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

    def tick(self,now=None):
        """定时任务入口：订单超时 + 全站清理。

        两部分保持在同一个事务里执行，避免订单超时与库存释放出现中间态。
        订单超时在 ``trade/orders.py``，非订单清理在本模块。
        """
        now=now or time.time()
        with self.tx() as c:
            self.tick_orders(c,now)
            self.tick_housekeeping(c,now)

    def tick_housekeeping(self,c,now):
        """非订单类的定期清理：会话、验证码、过期报价、超时客服会话。"""
        c.execute('DELETE FROM sessions WHERE expires<?',(now,))
        c.execute('DELETE FROM otp WHERE expires<?',(now-86400,))
        c.execute('DELETE FROM auth_attempts WHERE reset_at<?',(now-86400,))
        # 被接受的报价 24 小时未成交即作废，商品重新可报价（否则商品被一个
        # 永远不会结算的报价永久占住，其他人想买也买不了）。
        c.execute("UPDATE offers SET status='rejected' WHERE status='accepted' AND accepted_at<?",(now-86400,))
        # 客服会话 30 分钟没有新消息自动结束：用户关掉页面、客服下班、
        # 双方都不再说话时，会话不该永远挂在列表里。归档后重新咨询开新一轮。
        for r in c.execute("SELECT * FROM rooms WHERE support=1 AND COALESCE(support_status,'open')='open'").fetchall():
            last=c.execute('SELECT MAX(created) t FROM messages WHERE room_id=? AND removed<>3',(r['id'],)).fetchone()['t'] or r['created'] or now
            if now-last>1800:self._close_support(c,dict(r),'timeout')

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
