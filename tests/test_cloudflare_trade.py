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

    async def test_request_key_rejects_different_want_id(self):
        """同一下单键改变求购关联时必须冲突，避免费用与求购状态串单。"""
        self.db.execute("INSERT INTO wants(id,user_id,keyword,budget,status,created) VALUES(71,2,'测试求购',2000,'open',?)", (time.time(),))
        self.db.commit()
        first = await self.req('/api/checkout', method='POST', body={
            'product_ids': [10], 'delivery': 'delivery', 'address': 'A2',
            'appointment': self.appointment, 'key': 'want-replay', 'want_id': 71,
        })
        self.assertEqual(first.status, 200, first.body)
        replay = await self.checkout('want-replay')
        self.assertEqual(replay.status, 409, replay.body)

    async def test_replay_uses_original_request_after_order_edit(self):
        """订单编辑不改变原请求身份，原提交可重试，新内容必须换键。"""
        first = await self.checkout('edited', [10, 11])
        self.assertEqual(first.status, 200, first.body)
        changed = await self.req('/api/order/update', method='POST', body={
            'id': first.body['id'], 'product_ids': [10],
        })
        self.assertEqual(changed.status, 200, changed.body)
        replay = await self.checkout('edited', [10, 11])
        self.assertEqual(replay.status, 200, replay.body)
        self.assertEqual(replay.body['id'], first.body['id'])
        different = await self.checkout('edited', [10])
        self.assertEqual(different.status, 409, different.body)

    async def test_replay_after_appointment_window_keeps_original_result(self):
        """已成功请求在预约时间过后重试，仍返回同一订单。"""
        first = await self.checkout('expired-replay')
        self.assertEqual(first.status, 200, first.body)
        with patch('app.cloudflare.trade_api.time.time', return_value=self.appointment + 120):
            replay = await self.checkout('expired-replay')
        self.assertEqual(replay.status, 200, replay.body)
        self.assertEqual(replay.body['id'], first.body['id'])

    async def test_unknown_result_rejects_different_payload_for_existing_key(self):
        """模拟首次读漏掉订单，提交异常恢复时仍校验原请求内容。"""
        first = await self.checkout('unknown-result')
        self.assertEqual(first.status, 200, first.body)
        original_first = self.api.db.first
        reads = 0
        async def miss_existing(sql, params=()):
            """仅首次查询隐藏已存订单，模拟提交结果未知后的读竞态。"""
            nonlocal reads
            if 'WHERE buyer_id=? AND request_key=?' in sql:
                reads += 1
                if reads == 1:
                    return None
            return await original_first(sql, params)
        with patch.object(self.api.db, 'first', miss_existing):
            changed = await self.checkout('unknown-result', [11])
        self.assertEqual(changed.status, 409, changed.body)

    async def test_twenty_item_checkout_guard_stays_within_d1_bind_limit(self):
        """20 件商品整体下单，检查事务守卫的单语句绑定数未超预算。"""
        payload = json.dumps({'description': '合成图片', 'photos': [{'url': '/assets/item0.svg'}]})
        self.db.executemany(
            "INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,data,created) "
            "VALUES(?,3,'测试书','books',1200,200,'both','A1',?,?)",
            [(product_id, payload, time.time()) for product_id in range(12, 30)],
        )
        self.db.commit()
        original = self.api.db.guarded_batch
        async def inspect(guard_sql, guard_params, statements, *args, **kwargs):
            """提交前记录参数预算，并继续执行真实的内存事务适配。"""
            self.assertLessEqual(len(guard_params), 100)
            return await original(guard_sql, guard_params, statements, *args, **kwargs)
        with patch.object(self.api.db, 'guarded_batch', inspect):
            response = await self.checkout('twenty', list(range(10, 30)))
        self.assertEqual(response.status, 200, response.body)
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
