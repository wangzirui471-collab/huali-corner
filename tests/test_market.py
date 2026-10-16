import unittest, tempfile, sys, io, time, concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from app.market import Market, DomainError
from PIL import Image

class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.m=Market(self.tmp.name)
        self.a=self.login('13800000011'); self.b=self.login('13800000012'); self.staff=self.login('13800000003')
    def tearDown(self): self.tmp.cleanup()
    def login(self,phone):
        code=self.m.request_code(phone)['demo_code']
        return self.m.login(phone,code)['user']['id']
    def photos(self,u):
        result=[]
        for angle,color in zip(['front','side','top'],['red','green','blue']):
            b=io.BytesIO();Image.new('RGB',(100,100),color).save(b,'PNG')
            result.append(self.m.add_upload(u,b.getvalue(),angle)['id'])
        return result
    def listing(self,u=None,**extra):
        u=u or self.a
        data=dict(title='高等数学 第七版',category='books',price=1500,delivery_fee=300,delivery='both',region='A1楼下',description='实拍教材',photos=self.photos(u),college='计算机工程学院',edition='第七版',publisher='高等教育出版社',condition='有少量笔记',notes='少量',missing='无缺页',accessories='无附件',bought='2024-09',original_price=4500)
        data.update(extra)
        return self.m.publish(u,data)['id']
    def checkout(self,ids=None):
        return self.m.checkout(self.b,dict(product_ids=ids or [self.listing()],delivery='delivery',address='A2楼下',appointment=time.time()+7200,key='test-'+str(time.time_ns())))
    def test_otp_once_and_public_profile_no_phone(self):
        c=self.m.request_code('13800000090')['demo_code']
        r=self.m.login('13800000090',c)
        with self.assertRaises(DomainError):self.m.login('13800000090',c)
        self.assertNotIn('phone',self.m.profile(r['user']['id']))
    def test_three_angles_and_ownership(self):
        with self.assertRaises(DomainError):self.listing(photos=self.photos(self.a)[:2])
        with self.assertRaises(DomainError):self.listing(photos=self.photos(self.b))
        photos=self.photos(self.a)
        with self.assertRaises(DomainError):self.listing(photos=[photos[0]]*3)
    def test_no_negative_or_fractional_money(self):
        for price in [-1,1.5,True]:
            with self.assertRaises(DomainError):self.listing(price=price)
    def test_credit_below60_blocks_without_report_auto_penalty(self):
        p=self.listing(); t=self.m.create_ticket(self.b,dict(type='report',subject='商品问题',body='描述待核实',product_id=p))
        self.assertEqual(self.m.profile(self.a)['score'],100)
        with self.assertRaises(DomainError):self.m.credit_action(self.b,self.a,-50,'违规属实',t['id'])
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='resolved',reason='举报证据核实，卖家发布内容违规'))
        self.m.credit_action(self.staff,self.a,-50,'审核证据认定恶意发布',t['id'])
        with self.assertRaises(DomainError): self.listing()
        self.assertEqual(self.m.profile(self.a)['score'],50)
        appeal=self.m.create_ticket(self.a,dict(type='appeal',subject='信誉申诉',body='请求复核'))
        self.assertEqual(appeal['status'],'open')
    def test_combined_same_seller_fee_once_and_stock(self):
        p=self.listing();q=self.listing(title='Python教材',delivery_fee=500)
        o=self.checkout([p,q]);self.assertEqual(o['subtotal'],3000);self.assertEqual(o['delivery_fee'],500);self.assertEqual(o['total'],3500)
        with self.assertRaises(DomainError):self.checkout([p])
    def test_different_seller_no_combine(self):
        with self.assertRaises(DomainError):self.checkout([self.listing(),self.listing(self.staff)])
    def test_checkout_key_idempotent(self):
        p=self.listing();d=dict(product_ids=[p],delivery='pickup',address='',appointment=time.time()+7200,key='same')
        x=self.m.checkout(self.b,d);y=self.m.checkout(self.b,d);self.assertEqual(x['id'],y['id'])
    def test_payment_settlement_and_refund_journal(self):
        o=self.checkout();oid=o['id']
        self.m.order_action(self.b,oid,'pay',{})
        self.m.order_action(self.b,oid,'pay',{})
        self.m.order_action(self.a,oid,'deliver',{})
        self.m.tick(time.time()+90000)
        self.assertNotEqual(self.m.order(self.b,oid)['status'],'completed')
        self.m.order_action(self.b,oid,'handover',{})
        self.m.order_action(self.b,oid,'receive',{})
        self.m.order_action(self.b,oid,'receive',{})
        ledger=self.m.order(self.b,oid)['ledger']
        self.assertEqual([x['kind'] for x in ledger].count('payment'),1)
        self.assertEqual([x['kind'] for x in ledger].count('settlement'),1)
        with self.assertRaises(DomainError):self.m.order(self.login('13800000019'),oid)
        t=self.m.create_ticket(self.b,dict(type='refund',order_id=oid,subject='错版',body='实际交付不是约定版次'))
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='refund',reason='双方同意退货并已核实交接',amount=o['total']))
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='refund',reason='重复提交不重复退款',amount=o['total']))
        self.assertEqual(len([x for x in self.m.order(self.b,oid)['ledger'] if x['kind']=='refund']),1)
    def test_dispute_freezes_auto_receipt(self):
        o=self.checkout();self.m.order_action(self.b,o['id'],'pay',{});self.m.order_action(self.a,o['id'],'deliver',{});self.m.order_action(self.b,o['id'],'handover',{})
        self.m.create_ticket(self.b,dict(type='refund',order_id=o['id'],subject='缺页',body='待处理'))
        self.m.tick(time.time()+90000)
        self.assertEqual(self.m.order(self.b,o['id'])['status'],'disputed')
    def test_auto_receipt_after_acknowledged_handover(self):
        o=self.checkout();self.m.order_action(self.b,o['id'],'pay',{});self.m.order_action(self.a,o['id'],'deliver',{});self.m.order_action(self.b,o['id'],'handover',{})
        self.m.tick(time.time()+86410)
        self.assertEqual(self.m.order(self.b,o['id'])['status'],'completed')
    def test_cancel_unpaid_releases_stock(self):
        p=self.listing();o=self.checkout([p]);self.m.order_action(self.b,o['id'],'cancel',{})
        self.assertEqual(self.m.product(p)['status'],'available')
    def test_concurrent_checkout_one_winner(self):
        """三个线程抢同一件商品，最终只能存在一张订单。

        断言的是「数据库里的订单数」和「不同订单 id 的个数」，而不是
        「返回非空结果的个数」。原因是：checkout 对相同 request_key 是幂等的
        （会返回已存在的那张订单），而本 helper 用 time.time_ns() 生成键，
        并发时可能撞到同一个值 —— 于是多个线程都拿到同一个订单 id。
        那是正确行为，不是超卖。早先按「非空个数」断言，会把这个正常情况
        误报成失败，也会掩盖真正需要检查的不变量。
        """
        p=self.listing()
        def attempt(_):
            try:return self.checkout([p])['id']
            except DomainError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(attempt,range(3)))
        self.assertEqual(self.m.row('SELECT COUNT(*) n FROM orders')['n'],1,'同一件商品不应生成多张订单')
        self.assertEqual(len({x for x in results if x is not None}),1,'成功的线程必须指向同一张订单')

    def test_concurrent_checkout_distinct_keys_no_oversell(self):
        """用互不相同的请求键并发抢购，确认不会卖出两次。

        与上一个测试的区别：这里每个线程用独立 key，排除幂等返回的干扰，
        直接检验「一件实物只能产生一张订单」这个核心不变量。
        """
        p=self.listing()
        def attempt(i):
            try:return self.m.checkout(self.b,dict(product_ids=[p],delivery='delivery',address='A2楼下',appointment=time.time()+7200,key='distinct-%d'%i))['id']
            except DomainError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(attempt,range(3)))
        self.assertEqual(self.m.row('SELECT COUNT(*) n FROM orders')['n'],1)
        self.assertEqual(len([x for x in results if x is not None]),1)
        self.assertEqual(self.m.product(p)['status'],'reserved')
    def test_favorite_like_idempotent_and_completed_only_review(self):
        p=self.listing();self.m.react(self.b,p,'favorite',True);self.m.react(self.b,p,'favorite',True)
        self.assertEqual(len(self.m.products(self.b,{'favorite':'1'})),1)
        with self.assertRaises(DomainError):self.m.review(self.b,999,5,'好')
    def test_private_chat_membership_and_blocks(self):
        r=self.m.private_room(self.a,self.b)
        self.m.send_message(self.a,r['id'],'你好','message1')
        self.m.send_message(self.a,r['id'],'你好','message1')
        self.assertEqual(len(self.m.messages(self.b,r['id'])),1)
        with self.assertRaises(DomainError):self.m.messages(self.staff,r['id'])
        self.m.block(self.b,self.a,True)
        with self.assertRaises(DomainError):self.m.send_message(self.a,r['id'],'再联系','message2')
    def test_groups_split500_and_no_auto_join(self):
        self.assertEqual(self.m.rooms(self.a)['joined'],[])
        r=self.m.join_room(self.a,'college')
        with self.m.tx() as c:
            for i in range(499):
                u=c.execute('INSERT INTO users(phone,nickname,college) VALUES(?,?,?)',(f'159{i:08d}',f'test{i}','计算机工程学院')).lastrowid
                c.execute('INSERT INTO members(room_id,user_id) VALUES(?,?)',(r['id'],u))
        r2=self.m.join_room(self.b,'college');self.assertNotEqual(r['id'],r2['id'])
        self.assertEqual(self.m.join_room(self.b,'college')['id'],r2['id'])
        self.assertEqual(self.m.rooms(self.b)['joined'][0]['count'],1)
    def test_credit_cannot_punish_unrelated_user_or_duplicate_event(self):
        p=self.listing();t=self.m.create_ticket(self.b,dict(type='report',product_id=p,subject='发布问题',body='证据说明'))
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='resolved',reason='核实卖家发布违规'))
        with self.assertRaises(DomainError):self.m.credit_action(self.staff,self.b,-10,'不能处罚无关举报者',t['id'])
        self.m.credit_action(self.staff,self.a,-10,'已核实证据',t['id'])
        with self.assertRaises(DomainError):self.m.credit_action(self.staff,self.a,-10,'重复扣分',t['id'])
        self.assertEqual(self.m.profile(self.a)['score'],90)
    def test_refund_after_settlement_reconciles_and_media_in_backup(self):
        o=self.checkout();oid=o['id']
        self.m.order_action(self.b,oid,'pay',{});self.m.order_action(self.a,oid,'deliver',{});self.m.order_action(self.b,oid,'receive',{})
        t=self.m.create_ticket(self.b,dict(type='refund',order_id=oid,subject='退款',body='双方同意退货'))
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='refund',reason='核实退款',amount=o['total']))
        row=self.m.reconcile(self.staff)[0]
        self.assertEqual(row['held'],0);self.assertEqual(row['net_settlement'],0)
        import zipfile
        path=self.m.backup(self.staff)
        with zipfile.ZipFile(path) as archive:
            self.assertIn('market.sqlite3',archive.namelist())
            self.assertTrue(any(x.startswith('uploads/') for x in archive.namelist()))
    def test_admin_cannot_judge_own_product_or_product_linked_purchase(self):
        own=self.listing(self.staff)
        t=self.m.create_ticket(self.b,dict(type='report',product_id=own,subject='举报',body='平台管理员自己的商品'))
        with self.assertRaises(DomainError):self.m.resolve_ticket(self.staff,t['id'],dict(outcome='resolved',reason='自己不能审核自己'))
        other=self.listing()
        self.m.checkout(self.staff,dict(product_ids=[other],delivery='pickup',appointment=time.time()+7200,key='admin-purchase'))
        report=self.m.create_ticket(self.b,dict(type='report',product_id=other,subject='投诉商品',body='管理员参与该商品交易'))
        with self.assertRaises(DomainError):self.m.resolve_ticket(self.staff,report['id'],dict(outcome='resolved',reason='存在交易利益冲突'))
    def test_schedule_confirmation_and_structured_reschedule(self):
        o=self.checkout();oid=o['id'];self.m.order_action(self.b,oid,'pay',{})
        self.m.order_action(self.a,oid,'confirm_schedule',{})
        self.m.order_action(self.b,oid,'reschedule',{'appointment':time.time()+14400,'address':'A3楼下入口'})
        changes=self.m.order(self.a,oid)['changes'];self.assertEqual(len(changes),1)
        self.assertNotEqual(self.m.order(self.a,oid)['address'],'A3楼下入口')
        self.m.respond_change(self.a,changes[0]['id'],True)
        self.assertEqual(self.m.order(self.b,oid)['address'],'A3楼下入口')
    def test_unconfirmed_schedule_refunds_after24h(self):
        o=self.checkout();self.m.order_action(self.b,o['id'],'pay',{})
        self.m.tick(time.time()+86410)
        self.assertEqual(self.m.order(self.b,o['id'])['status'],'cancelled')
        self.assertEqual(self.m.reconcile(self.staff)[0]['held'],0)
    def test_backup_restores_data(self):
        p=self.listing();path=self.m.backup(self.staff)
        self.assertTrue(Path(path).exists())
        self.assertEqual(Market(self.tmp.name).product(p)['title'],'高等数学 第七版')

if __name__=='__main__':unittest.main()
