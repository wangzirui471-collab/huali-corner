"""运维模块：模拟资金对账、数据库一致性备份。"""
import json, sqlite3, tempfile, time, zipfile
from contextlib import closing
from ..core.errors import ValidationMixin, DomainError
from pathlib import Path


class OpsService(ValidationMixin):
    def reconcile(self,u):
        self.staff(u);result=[]
        for o in self.rows('SELECT id,total,status FROM orders ORDER BY id DESC'):
            amounts={r['kind']:r['amount'] for r in self.rows('SELECT kind,amount FROM ledger WHERE order_id=?',(o['id'],))}
            net=amounts.get('settlement',0)-amounts.get('settlement_reversal',0)
            held=amounts.get('payment',0)-amounts.get('refund',0)-net
            result.append({**o,'payment':amounts.get('payment',0),'refund':amounts.get('refund',0),'net_settlement':net,'held':held,'consistent':held>=0 and (o['status'] not in ['completed','refunded','partial_refunded','cancelled'] or held==0),'simulation':True})
        return result

    def backup(self,u):
        self.staff(u);return self._backup()

    def _backup(self):
        directory=self.root/'backups';directory.mkdir(exist_ok=True);path=directory/f'market-{time.time_ns()}.zip'
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/'market.sqlite3'
            # SQLite's transaction context does not close the connection. Windows
            # requires every snapshot handle to be closed before temporary cleanup.
            with closing(self.connect()) as source,closing(sqlite3.connect(dbpath)) as dest:
                source.backup(dest)
            with closing(sqlite3.connect(dbpath)) as snapshot:
                uploads=snapshot.execute('SELECT path FROM uploads').fetchall()
                # 头像清单也从这同一个快照读：另开一个 live 连接去查，可能把比库里
                # 新的文件写进包，恢复后就会指向一个数据库里不存在的 upload_id。
                avatars=self.user_avatar_backup_entries(snapshot)
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.write(dbpath,'market.sqlite3')
                for upload in uploads:
                    file=Path(upload[0]);archive.write(file,'uploads/'+file.name)
                for avatar,relative in avatars:archive.write(avatar,relative)
                archive.writestr('manifest.json',json.dumps({'simulation':True,'created':time.time(),'files':len(uploads)+len(avatars),'restore':'Stop server. Extract SQLite and uploads to an empty data directory; uploads paths are rebound on startup.'}))
        return str(path)
