"""Synthetic in-memory staff/support Cloudflare integration tests; no deployed data."""
import csv
import io
import json
import zipfile
from unittest.mock import patch
from cloudflare_test_support import CloudCase, Binding, TestResponse
from app.cloudflare.api import Api, ROUTES
from app.cloudflare.staff_api import StaffApi, STAFF_ROUTES
from app.cloudflare.crypto import ROUNDS

class StaffTests(CloudCase):
    def setUp(self):
        super().setUp()
        for target in ('app.cloudflare.staff_api.Response', 'app.cloudflare.http.Response'):
            response_patch = patch(target, TestResponse); response_patch.start(); self.addCleanup(response_patch.stop)
        if not isinstance(self.api, StaffApi): self.api.__class__ = type('StaffTestApi', (StaffApi, Api), {})
        self.routes = patch.dict(ROUTES, STAFF_ROUTES); self.routes.start(); self.addCleanup(self.routes.stop)
        self.db.execute("INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,status,data) VALUES(10,3,'测试物品','living',1000,0,'pickup','A1','reserved','{}')")
        self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,items,total,status,created) VALUES(10,2,3,?,1000,'paid',1)", (json.dumps([{'id':10,'title':'测试物品','price':1000}]),))
        self.db.execute("INSERT INTO ledger(order_id,kind,amount,created) VALUES(10,'payment',1000,1)")
        self.db.execute("INSERT INTO tickets(id,user_id,order_id,product_id,type,subject,body,created) VALUES(10,2,10,10,'report','测试工单','说明',1)")
        self.db.execute("INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(10,4,'内部处理依据',1,1)")
        self.db.executemany('INSERT INTO password_credentials VALUES(?,?,?,?,?)',[(i,'a'*32,'b'*64,ROUNDS,'c'*64) for i in (1,2,3,4,5)])
        self.db.commit()

    async def post(self, path, body, uid=1): return await self.req(path, uid=uid, method='POST', body=body)

    async def test_route_methods_and_all_admin_reads(self):
        for path in ('/api/admin/staff','/api/admin/accounts','/api/admin/sellers','/api/moderation/words','/api/user/dossier?id=2','/api/audit/export'):
            with self.subTest(path=path):
                self.assertEqual((await self.req(path, uid=2)).status,403)
                r=await self.req(path,uid=1); self.assertEqual(r.status,200,r.body)
        self.assertEqual((await self.req('/api/admin/staff/status',uid=1)).status,405)
        self.assertEqual((await self.req('/api/ticket?id=10',uid=0)).status,401)

    async def test_ticket_privacy_internal_replies_and_notifications(self):
        t=(await self.req('/api/ticket?id=10')).body; self.assertEqual(t['messages'],[])
        self.assertEqual((await self.req('/api/ticket?id=10',uid=4)).body['messages'][0]['body'],'内部处理依据')
        self.assertEqual((await self.req('/api/ticket?id=10',uid=1)).status,200)
        self.db.execute("INSERT INTO users(id,phone,nickname) VALUES(6,'outsider@test.invalid','外人')")
        self.db.execute("INSERT INTO sessions VALUES(?,6,9999999999)",(__import__('app.cloudflare.crypto',fromlist=['session_digest']).session_digest('test-6'),))
        self.assertEqual((await self.req('/api/ticket?id=10',uid=6)).status,403)
        self.assertEqual((await self.post('/api/ticket/reply',{'id':10,'body':'越权备注','internal':True},uid=2)).status,403)
        r=await self.post('/api/ticket/reply',{'id':10,'body':'公开回复'},uid=4); self.assertEqual(r.status,200,r.body)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM notifications WHERE kind='ticket_reply'").fetchone()[0],2)
        rows=(await self.req('/api/tickets')).body; self.assertEqual(len(rows),1); self.assertTrue(all(not m['internal'] for m in rows[0]['messages']))

    async def test_refund_creation_duplicate_and_product_order_matching(self):
        r=await self.post('/api/tickets',{'type':'refund','order_id':10,'product_id':10,'subject':'退款','body':'有问题'},uid=2)
        self.assertEqual(r.status,200,r.body); self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'disputed')
        self.assertEqual((await self.post('/api/tickets',{'type':'refund','order_id':10,'subject':'重复','body':'重复'},uid=2)).status,409)
        self.assertEqual((await self.post('/api/tickets',{'type':'refund','order_id':10,'subject':'卖方申请','body':'错误'},uid=3)).status,400)
        self.assertEqual((await self.post('/api/tickets',{'type':'report','product_id':10,'subject':'举报','body':'说明'},uid=2)).body['order_id'],10)
        self.db.execute("INSERT INTO products(id,seller_id,status,data) VALUES(11,3,'available','{}')")
        self.assertEqual((await self.post('/api/tickets',{'type':'report','product_id':11,'order_id':10,'subject':'错绑','body':'说明'},uid=2)).status,400)

    async def test_candidates_and_link_order_scoped_to_product(self):
        self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,items,total,status) VALUES(11,2,3,'[]',100,'paid')")
        r=await self.req('/api/ticket/candidates?id=10',uid=4); self.assertEqual(r.status,200,r.body); self.assertEqual([x['id'] for x in r.body],[10])
        self.assertEqual((await self.post('/api/ticket/link-order',{'id':10,'order_id':11},uid=4)).status,400)
        self.assertEqual((await self.post('/api/ticket/link-order',{'id':10,'order_id':10},uid=4)).status,200)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='ticket_link_order'").fetchone()[0],1)

    async def test_claim_review_reject_and_conflicts(self):
        for outcome in ('claim','review'):
            r=await self.post('/api/ticket/resolve',{'id':10,'outcome':outcome,'reason':'处理依据'},uid=4); self.assertEqual(r.status,200,r.body)
        self.assertEqual((await self.post('/api/ticket/resolve',{'id':10,'outcome':'resolved','reason':'自己交易'},uid=3)).status,403)
        self.db.execute("UPDATE users SET role='support' WHERE id=3")
        self.assertEqual((await self.post('/api/ticket/resolve',{'id':10,'outcome':'resolved','reason':'自己交易'},uid=3)).status,403)
        self.db.execute("UPDATE tickets SET type='refund' WHERE id=10"); self.db.execute("UPDATE orders SET status='disputed' WHERE id=10")
        r=await self.post('/api/ticket/resolve',{'id':10,'outcome':'reject','reason':'已核实'},uid=4); self.assertEqual(r.status,200,r.body)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'paid')

    async def test_partial_refund_updates_every_domain_atomically(self):
        self.db.execute("UPDATE tickets SET type='refund' WHERE id=10"); self.db.execute("UPDATE orders SET status='disputed',want_id=1 WHERE id=10")
        self.db.execute("INSERT INTO wants(id,user_id,keyword,budget,status) VALUES(1,2,'物品',1000,'matched')")
        self.db.execute("INSERT INTO ledger(order_id,kind,amount) VALUES(10,'service_fee',50)")
        r=await self.post('/api/ticket/resolve',{'id':10,'outcome':'refund','amount':400,'reason':'部分退款'},uid=4); self.assertEqual(r.status,200,r.body)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'partial_refunded')
        self.assertEqual(dict(self.db.execute('SELECT kind,amount FROM ledger WHERE order_id=10').fetchall()),{'payment':1000,'refund':400,'settlement':600,'service_fee':50,'service_fee_reversal':50})
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'removed')
        self.assertEqual(self.db.execute('SELECT status FROM wants WHERE id=1').fetchone()[0],'open')
        self.assertEqual(self.db.execute('SELECT status FROM tickets WHERE id=10').fetchone()[0],'resolved')
        self.assertEqual((await self.post('/api/ticket/resolve',{'id':10,'outcome':'refund','amount':400,'reason':'重试'},uid=4)).status,200)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='ticket_refund'").fetchone()[0],1)

    async def test_refund_failure_rolls_back_ticket_ledger_and_notifications(self):
        self.db.execute("UPDATE tickets SET type='refund' WHERE id=10"); self.db.execute("UPDATE orders SET status='disputed' WHERE id=10")
        self.db.execute("CREATE TRIGGER fail_refund_audit BEFORE INSERT ON audit WHEN NEW.type='ticket_refund' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        r=await self.post('/api/ticket/resolve',{'id':10,'outcome':'refund','reason':'全退'},uid=4); self.assertEqual(r.status,500)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'disputed')
        self.assertEqual(self.db.execute('SELECT status FROM tickets WHERE id=10').fetchone()[0],'open')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ledger WHERE kind='refund'").fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM notifications').fetchone()[0],0)

    async def test_stale_ticket_guard_aborts_every_write(self):
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kwargs):
            self.db.execute("UPDATE tickets SET status='resolved' WHERE id=10")
            return await original(sql,params,statements,**kwargs)
        with patch.object(self.api.db,'guarded_batch',race):
            r=await self.post('/api/ticket/resolve',{'id':10,'outcome':'claim','reason':'领取'},uid=4)
        self.assertEqual(r.status,409,r.body); self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0],0)

    async def test_credit_preview_permission_related_target_and_duplicate(self):
        preview={'target':3,'ticket_id':10,'violation':'severe','dry_run':True,'reason':'核实'}
        self.assertEqual((await self.post('/api/credit',preview,uid=4)).status,403)
        r=await self.post('/api/credit',preview); self.assertEqual(r.status,200,r.body); self.assertEqual(r.body['suggested'],15)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0],0)
        self.db.execute("UPDATE tickets SET status='resolved' WHERE id=10")
        data={'target':3,'ticket_id':10,'delta':-15,'reason':'已核实违规'}
        self.assertEqual((await self.post('/api/credit',data)).status,200)
        self.assertEqual((await self.post('/api/credit',data)).status,409)
        self.assertEqual(self.db.execute('SELECT score FROM users WHERE id=3').fetchone()[0],85)
        hist=await self.req('/api/credit/history',uid=3); self.assertEqual(hist.body[0]['kind'],'credit')

    async def test_review_award_caps_and_no_duplicate_high_rating_award(self):
        self.db.execute("UPDATE orders SET status='completed' WHERE id=10"); self.db.execute('UPDATE users SET score=90 WHERE id=3')
        data={'order_id':10,'rating':5,'body':'很好'}
        self.assertEqual((await self.post('/api/review',data,uid=4)).status,400)
        self.assertEqual((await self.post('/api/review',data,uid=2)).status,200)
        self.assertEqual((await self.post('/api/review',data,uid=2)).status,200)
        self.assertEqual(self.db.execute('SELECT score FROM users WHERE id=3').fetchone()[0],91)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='credit'").fetchone()[0],1)

    async def test_staff_creation_requires_full_browser_kdf_and_role_boundary(self):
        data={'phone':'new@test.invalid','nickname':'新客服','role':'support','salt':'a'*32,'digest':'b'*64,'rounds':ROUNDS}
        self.assertEqual((await self.post('/api/admin/staff',data,uid=4)).status,403)
        self.assertEqual((await self.post('/api/admin/staff',{**data,'role':'admin'})).status,403)
        self.assertEqual((await self.post('/api/admin/staff',{**data,'rounds':10000})).status,400)
        r=await self.post('/api/admin/staff',data); self.assertEqual(r.status,200,r.body); self.assertTrue(r.body['recovery_code'])
        target=r.body['id']; self.assertEqual(self.db.execute('SELECT rounds FROM password_credentials WHERE user_id=?',(target,)).fetchone()[0],ROUNDS)
        self.assertEqual((await self.post('/api/admin/staff',data)).status,409)

    async def test_staff_status_password_and_sessions_enforce_hierarchy(self):
        self.assertEqual((await self.post('/api/admin/staff/status',{'id':1,'status':'disabled'})).status,403)
        self.assertEqual((await self.post('/api/admin/staff/status',{'id':5,'status':'disabled'})).status,403)
        self.assertEqual((await self.post('/api/admin/staff/status',{'id':4,'status':'disabled'})).status,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=4').fetchone()[0],0)
        data={'id':4,'salt':'d'*32,'digest':'e'*64,'rounds':ROUNDS}
        r=await self.post('/api/admin/staff/password',data); self.assertEqual(r.status,200,r.body); self.assertTrue(r.body['recovery_code'])
        self.assertEqual(self.db.execute('SELECT digest FROM password_credentials WHERE user_id=4').fetchone()[0],'e'*64)
        self.assertEqual((await self.post('/api/admin/staff/status',{'id':4,'status':'active'})).status,200)
        self.assertEqual((await self.post('/api/admin/session/revoke',{'id':2},uid=5)).body['revoked'],1)

    async def test_role_boundaries_and_immediate_session_revocation(self):
        self.assertEqual((await self.post('/api/admin/role',{'target':5,'role':'user'})).status,403)
        self.assertEqual((await self.post('/api/admin/role',{'target':2,'role':'admin'})).status,403)
        self.assertEqual((await self.post('/api/admin/role',{'target':2,'role':'support'})).status,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=2').fetchone()[0],0)
        self.assertEqual((await self.post('/api/admin/role',{'target':1,'role':'user'},uid=5)).status,200)

    async def test_dossier_is_admin_only_masked_and_audited_without_chat(self):
        self.assertEqual((await self.req('/api/user/dossier?id=2',uid=4)).status,403)
        r=await self.req('/api/user/dossier?id=2',uid=1); self.assertEqual(r.status,200,r.body)
        self.assertEqual(r.body['phone'],'u***@test.invalid'); self.assertNotIn('messages',r.body)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='dossier_view' AND target=2").fetchone()[0],1)

    async def test_seller_delist_aliases_only_available_and_audit(self):
        self.db.execute("INSERT INTO products(id,seller_id,status,data,promoted_until) VALUES(11,3,'available','{}',9999999999)")
        self.assertEqual((await self.post('/api/admin/sellers/moderate',{'seller_id':3,'reason':'违规'},uid=4)).status,403)
        r=await self.post('/api/admin/sellers/moderate',{'seller_id':3,'reason':'违规'}); self.assertEqual(r.status,200,r.body); self.assertEqual(r.body['ids'],[11])
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'reserved')
        self.assertEqual(tuple(self.db.execute('SELECT status,delisted_by,promoted_until FROM products WHERE id=11').fetchone()),('removed',1,0))

    async def test_content_remove_restore_and_self_conflict(self):
        self.db.execute("INSERT INTO posts(id,user_id,topic,body) VALUES(1,2,'分享','测试')")
        for action in ('remove','restore'):
            r=await self.post('/api/admin/content/action',{'kind':'post','id':1,'action':action,'reason':'核实'},uid=4); self.assertEqual(r.status,200,r.body)
        self.db.execute('UPDATE posts SET user_id=4 WHERE id=1')
        self.assertEqual((await self.post('/api/admin/content/action',{'kind':'post','id':1,'reason':'自己'},uid=4)).status,400)

    async def test_wordlist_mutations_reload_and_preserve_builtins(self):
        r=await self.post('/api/moderation/words',{'op':'add','word':'合成测试词','category':'测试','action':'review'}); self.assertEqual(r.status,200,r.body)
        r=await self.req('/api/moderation/words',uid=1); self.assertTrue(any(x['word']=='合成测试词' and x['level']=='中' for x in r.body['words']))
        self.assertEqual((await self.post('/api/moderation/words',{'op':'remove','word':'合成测试词'})).status,200)
        self.assertEqual((await self.post('/api/moderation/words',{'op':'remove','word':'加微信'})).status,200)
        self.assertIn('加微信',(await self.req('/api/moderation/words',uid=1)).body['disabled'])
        self.assertEqual((await self.post('/api/moderation/words',{'op':'restore','word':'加微信'})).status,200)
        self.assertNotIn('加微信',(await self.req('/api/moderation/words',uid=1)).body['disabled'])

    async def test_nomination_and_stars(self):
        self.db.execute('INSERT INTO members(room_id,user_id) VALUES(1,2)'); self.db.execute("INSERT INTO nominations(id,user_id,room_id,reason) VALUES(1,2,1,'合成申请')")
        self.assertEqual((await self.post('/api/admin/nominate',{'id':1},uid=5)).status,403)
        self.assertEqual((await self.post('/api/admin/nominate',{'id':1})).status,200)
        self.assertEqual(self.db.execute('SELECT role FROM members WHERE user_id=2').fetchone()[0],'moderator')
        r=await self.post('/api/admin/stars',{'target':2,'delta':2,'reason':'复核'}); self.assertEqual(r.status,200,r.body); self.assertEqual(r.body['stars'],6)
        self.assertEqual((await self.post('/api/admin/stars',{'target':5,'delta':1,'reason':'越权'})).status,403)

    async def test_ban_settles_seller_and_buyer_orders_and_unban(self):
        r=await self.post('/api/admin/ban',{'target':3,'reason':'合成封禁'}); self.assertEqual(r.status,200,r.body)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'disputed')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tickets WHERE type='refund' AND order_id=10").fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=3').fetchone()[0],0)
        r=await self.post('/api/admin/ban',{'target':3,'banned':False,'reason':'解封'}); self.assertEqual(r.status,200,r.body)
        self.db.execute("UPDATE orders SET status='paid' WHERE id=10")
        r=await self.post('/api/admin/ban',{'target':2,'reason':'买家封禁'}); self.assertEqual(r.status,200,r.body)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=10').fetchone()[0],'cancelled')
        self.assertEqual(self.db.execute("SELECT amount FROM ledger WHERE order_id=10 AND kind='refund'").fetchone()[0],1000)
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'available')

    async def test_purge_role_graded_and_anonymizes_synthetic_user(self):
        # 分级：开发者可清 admin/support/user；管理员可清 support/user；同级与上级不可清。
        # 用没有订单的账号验证权限：订单结算语句依赖 sqlite 的 JSON1，
        # 本机 Python 3.8 的 sqlite 没编该扩展（线上 D1 支持）。
        self.db.execute("INSERT INTO users(id,phone,nickname,role) VALUES(6,'u6@test.invalid','管理员乙','admin'),(7,'u7@test.invalid','普通用户乙','user')")
        self.assertEqual((await self.post('/api/admin/purge',{'target':7,'reason':'合成测试'},uid=4)).status,403)  # 客服越权
        self.assertEqual((await self.post('/api/admin/purge',{'target':6,'reason':'合成测试'},uid=1)).status,403)  # 管理员互删
        self.assertEqual((await self.post('/api/admin/purge',{'target':5,'reason':'合成测试'},uid=1)).status,403)  # 管理员删开发者
        r=await self.post('/api/admin/purge',{'target':7,'reason':'合成测试'},uid=1); self.assertEqual(r.status,200,r.body)  # 管理员清用户
        user=self.db.execute('SELECT phone,nickname,status FROM users WHERE id=7').fetchone(); self.assertEqual(user['status'],'deleted'); self.assertNotEqual(user['phone'],'u7@test.invalid')
        r=await self.post('/api/admin/purge',{'target':4,'reason':'合成测试'},uid=1); self.assertEqual(r.status,200,r.body)  # 管理员清客服
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=4').fetchone()[0],'deleted')
        r=await self.post('/api/admin/purge',{'target':1,'reason':'合成测试'},uid=5); self.assertEqual(r.status,200,r.body)  # 开发者清管理员
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=1').fetchone()[0],'deleted')

    async def test_csv_scope_bom_and_formula_safety(self):
        self.db.execute("INSERT INTO audit(actor,type,reason,created) VALUES(4,'synthetic','=DANGEROUS()',1),(1,'synthetic','private',1)")
        r=await self.req('/api/audit/export',uid=4); self.assertEqual(r.status,200,r.body)
        self.assertTrue(r.body.startswith(b'\xef\xbb\xbf')); self.assertIn(b"'=DANGEROUS()",r.body); self.assertNotIn(b'private',r.body)

    async def test_complete_backup_private_zip_includes_sql_media_and_restore_checksums(self):
        key='media/products/2/synthetic.webp'; self.bucket.objects[key]=b'synthetic media'
        self.db.execute("INSERT INTO friendships(requester,target,message,status,created) VALUES(2,3,'测试好友','accepted',1)")
        self.db.execute('INSERT INTO uploads(id,user_id,path,private) VALUES(?,?,?,1)',('u1',2,key))
        self.assertEqual((await self.post('/api/backup',{},uid=4)).status,403)
        r=await self.post('/api/backup',{}); self.assertEqual(r.status,200,r.body)
        self.assertEqual(r.headers['Cache-Control'],'private, no-store')
        with zipfile.ZipFile(io.BytesIO(r.body)) as archive:
            self.assertEqual(archive.read('r2/'+key),b'synthetic media')
            manifest=json.loads(archive.read('manifest.json')); self.assertEqual(manifest['media'],[key])
            import sqlite3
            restored=sqlite3.connect(':memory:'); self.addCleanup(restored.close)
            restored.executescript(archive.read('database.sql').decode('utf-8'))
            self.assertEqual(restored.execute('SELECT COUNT(*) FROM users').fetchone()[0],5)
            self.assertEqual(restored.execute('SELECT path FROM uploads').fetchone()[0],key)
            self.assertIn('friendships', manifest['tables'])
            friendship = restored.execute('SELECT requester,target,message,status FROM friendships').fetchone()
            self.assertEqual(friendship, (2, 3, '测试好友', 'accepted'))

    async def test_unknown_application_table_prevents_incomplete_backup(self):
        self.db.execute('CREATE TABLE future_records(id INTEGER PRIMARY KEY, body TEXT)')
        result = await self.post('/api/backup', {})
        self.assertEqual(result.status, 503, result.body)
        self.assertIn('备份表清单', result.body['error'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='backup'").fetchone()[0], 0)

    def test_backup_table_list_covers_every_schema_table(self):
        # 运行时的「备份表清单需随数据库迁移更新」守卫能拦住缺表备份，
        # 但得真点一次备份才发现。这里静态比对 schema.sql：
        # 以后迁移加表忘了补 BACKUP_TABLES，测试先红。
        import re
        from pathlib import Path
        from app.cloudflare.staff_api import BACKUP_TABLES
        schema = (Path(__file__).resolve().parents[1] / 'Backend mission' / 'app' / 'cloudflare' / 'schema.sql').read_text(encoding='utf-8')
        created = set(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', schema))
        self.assertEqual(created - set(BACKUP_TABLES), set(), 'schema.sql 有表没进备份清单')
        self.assertEqual(set(BACKUP_TABLES) - created, set(), '备份清单里有 schema.sql 不存在的表')

    async def test_missing_media_makes_backup_fail_without_false_success(self):
        self.db.execute("INSERT INTO uploads(id,user_id,path) VALUES('missing',2,'media/products/2/missing.webp')")
        r=await self.post('/api/backup',{}); self.assertEqual(r.status,404)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE type='backup'").fetchone()[0],0)

if __name__=='__main__':
    import unittest
    unittest.main()
