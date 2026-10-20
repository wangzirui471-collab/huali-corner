import json
import time
from unittest.mock import patch
from cloudflare_test_support import CloudCase

class TradeTests(CloudCase):
    def setUp(self):
        super().setUp()
        payload=json.dumps({'description':'真实规则的合成测试','photos':[{'url':'/assets/item0.svg'}]})
        self.db.executemany("INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,data,created) VALUES(?,3,'测试书','books',1200,200,'both','A1',?,?)",[(10,payload,time.time()),(11,payload,time.time())])
        self.db.commit()
        self.appointment=time.time()+7200
    async def checkout(self,key='one',ids=None):
        return await self.req('/api/checkout',body={'product_ids':ids or [10], 'delivery':'delivery','address':'A2','appointment':self.appointment,'key':key},method='POST')
    async def action(self,oid,action,uid=2,**data):
        return await self.req('/api/order/action',uid=uid,method='POST',body={'id':oid,'action':action,**data})
    async def test_checkout_idempotency_and_distinct_key_cannot_sell_twice(self):
        first=await self.checkout();self.assertEqual(first.status,200)
        second=await self.checkout();self.assertEqual(second.status,200)
        self.assertEqual(first.body['id'],second.body['id'])
        self.assertEqual((await self.checkout('other')).status,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
    async def test_trade_lifecycle_and_ledger_are_idempotent(self):
        order=(await self.checkout()).body;oid=order['id']
        self.assertEqual(order['total'],1400)
        self.assertEqual((await self.action(oid,'pay',uid=3)).status,403)
        self.assertEqual((await self.action(oid,'pay')).body['status'],'paid')
        self.assertEqual((await self.action(oid,'pay')).status,200)
        self.assertEqual((await self.action(oid,'deliver',uid=3)).body['status'],'awaiting_handover')
        self.assertEqual((await self.action(oid,'handover')).body['status'],'awaiting_receipt')
        self.assertEqual((await self.action(oid,'receive')).body['status'],'completed')
        self.assertEqual((await self.action(oid,'receive')).status,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ledger WHERE order_id=?',(oid,)).fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'sold')
    async def test_cancel_releases_only_active_seller_inventory(self):
        oid=(await self.checkout()).body['id']
        self.db.execute("UPDATE users SET status='banned' WHERE id=3");self.db.commit()
        self.assertEqual((await self.action(oid,'cancel')).body['status'],'cancelled')
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'removed')
    async def test_banned_seller_cannot_be_checked_out(self):
        self.db.execute("UPDATE users SET status='banned' WHERE id=3");self.db.commit()
        self.assertNotEqual((await self.checkout()).status,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
    async def test_modify_and_respond_to_reschedule(self):
        oid=(await self.checkout(ids=[10,11])).body['id']
        edited=await self.req('/api/order/update',method='POST',body={'id':oid,'product_ids':[10],'delivery':'pickup','appointment':time.time()+8000})
        self.assertEqual(edited.status,200);self.assertEqual(edited.body['total'],1200)
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=11').fetchone()[0],'available')
        await self.action(oid,'pay')
        self.assertEqual((await self.action(oid,'reschedule',appointment=time.time()+9000,address='图书馆')).status,200)
        cid=self.db.execute('SELECT id FROM order_changes').fetchone()[0]
        self.assertEqual((await self.req('/api/order/change',method='POST',body={'id':cid,'accept':True})).status,403)
        self.assertEqual((await self.req('/api/order/change',uid=3,method='POST',body={'id':cid,'accept':True})).status,200)
    async def test_details_deny_unrelated_user_but_allow_staff(self):
        oid=(await self.checkout()).body['id']
        self.assertEqual((await self.req('/api/order?id='+str(oid),uid=4)).status,200)
        self.assertEqual((await self.req('/api/order?id='+str(oid),uid=5)).status,200)
        self.db.execute("INSERT INTO users(id,phone,nickname) VALUES(7,'other@test.invalid','旁人')")
        from app.cloudflare.crypto import session_digest
        self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(session_digest('test-7'),7,9999999999));self.db.commit()
        self.assertEqual((await self.req('/api/order?id='+str(oid),uid=7)).status,403)
    async def test_order_and_stock_roll_back_if_notification_write_fails(self):
        self.db.execute("CREATE TRIGGER reject_notify BEFORE INSERT ON notifications BEGIN SELECT RAISE(ABORT,'test failure'); END;")
        self.db.commit()
        self.assertNotEqual((await self.checkout()).status,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'available')
    async def test_timer_does_not_settle_open_refund_ticket(self):
        oid=(await self.checkout()).body['id']
        await self.action(oid,'pay');await self.action(oid,'deliver',uid=3);await self.action(oid,'handover')
        self.db.execute('UPDATE orders SET handover_at=? WHERE id=?',(time.time()-90000,oid))
        self.db.execute("INSERT INTO tickets(user_id,order_id,type,subject,body,status) VALUES(2,?,'refund','售后','测试','open')",(oid,));self.db.commit()
        await self.api.cf_trade_tick(time.time())
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()[0],'awaiting_receipt')

    async def test_checkout_disabled_buyer_race_cannot_reserve_inventory(self):
        original=self.api.db.guarded_batch
        async def race(*a,**kw):
            self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
            return await original(*a,**kw)
        with patch.object(self.api.db,'guarded_batch',race):r=await self.checkout()
        self.assertEqual(r.status,409,r.body)
        self.assertEqual(self.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'available')
    async def test_pay_disabled_buyer_race_cannot_write_payment(self):
        oid=(await self.checkout()).body['id'];original=self.api.db.guarded_batch
        async def race(*a,**kw):
            self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
            return await original(*a,**kw)
        with patch.object(self.api.db,'guarded_batch',race):r=await self.action(oid,'pay')
        self.assertEqual(r.status,409,r.body)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ledger WHERE kind='payment'").fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()[0],'awaiting_payment')
    async def test_request_key_rejects_different_product_or_delivery_payload(self):
        original=await self.checkout();self.assertEqual(original.status,200)
        for changed in ({'product_ids':[11]},{'delivery':'pickup'},{'address':'B1'},{'appointment':self.appointment+600}):
            payload={'product_ids':[10],'delivery':'delivery','address':'A2','appointment':self.appointment,'key':'one',**changed}
            r=await self.req('/api/checkout',method='POST',body=payload)
            self.assertEqual(r.status,409,(changed,r.body))
        self.assertEqual(self.db.execute('SELECT count(*) FROM orders').fetchone()[0],1)
    async def test_checkout_honors_other_buyers_live_accepted_offer(self):
        self.db.execute("INSERT INTO offers(product_id,buyer_id,amount,status,created,accepted_at) VALUES(10,4,500,'accepted',?,?)",(time.time(),time.time()))
        r=await self.checkout();self.assertEqual(r.status,409,r.body)
        self.assertEqual(self.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
    async def test_checkout_does_not_apply_expired_accepted_discount(self):
        self.db.execute("INSERT INTO offers(product_id,buyer_id,amount,status,created,accepted_at) VALUES(10,2,500,'accepted',?,?)",(time.time()-90000,time.time()-90000))
        r=await self.checkout();self.assertEqual(r.status,200,r.body);self.assertEqual(r.body['subtotal'],1200)
    async def test_checkout_live_offer_accept_race_cannot_be_bypassed(self):
        original=self.api.db.guarded_batch
        async def race(*a,**kw):
            self.db.execute("INSERT INTO offers(product_id,buyer_id,amount,status,created,accepted_at) VALUES(10,4,500,'accepted',?,?)",(time.time(),time.time()))
            return await original(*a,**kw)
        with patch.object(self.api.db,'guarded_batch',race):r=await self.checkout()
        self.assertEqual(r.status,409,r.body);self.assertEqual(self.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
