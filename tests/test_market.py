import unittest, tempfile, sys, io, time, concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from app.market import Market, DomainError
from PIL import Image

class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.m=Market(self.tmp.name)
        self.a=self.login('13800000011'); self.b=self.login('13800000012'); self.staff=self.login('19065322759')
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
        befriend(self.m,self.a,self.b)
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
        self.m.order_action(self.b,oid,'pay',{});self.m.order_action(self.a,oid,'deliver',{});self.m.order_action(self.b,oid,'handover',{});self.m.order_action(self.b,oid,'receive',{})
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
    def test_offer_cannot_be_zero_or_at_or_above_price(self):
        p=self.listing()  # price=1500 分
        with self.assertRaises(DomainError):self.m.offer(self.b,p,0)
        with self.assertRaises(DomainError):self.m.offer(self.b,p,1500)
        with self.assertRaises(DomainError):self.m.offer(self.b,p,1600)
        self.m.offer(self.b,p,1000)
    def test_accept_offer_rejects_when_product_unavailable(self):
        p=self.listing();oid=self.m.offer(self.b,p,1000)['id']
        self.m.set_product_status(self.a,p,'delist')
        with self.assertRaises(DomainError):self.m.accept_offer(self.a,oid,True)
        self.m.accept_offer(self.a,oid,False)
        self.assertEqual(self.m.offers(self.a)[0]['status'],'rejected')
    def test_receive_requires_handover_first(self):
        o=self.checkout();oid=o['id']
        self.m.order_action(self.b,oid,'pay',{});self.m.order_action(self.a,oid,'deliver',{})
        with self.assertRaises(DomainError):self.m.order_action(self.b,oid,'receive',{})
        self.m.order_action(self.b,oid,'handover',{});self.m.order_action(self.b,oid,'receive',{})
        self.assertEqual(self.m.order(self.b,oid)['status'],'completed')
    def test_first_joiner_becomes_college_group_owner(self):
        room=self.m.join_room(self.b,'college')
        self.assertEqual(self.m.row('SELECT role FROM members WHERE room_id=? AND user_id=?',(room['id'],self.b))['role'],'owner')
        room2=self.m.join_room(self.a,'college')
        self.assertEqual(room2['id'],room['id'])
        self.assertEqual(self.m.row('SELECT role FROM members WHERE room_id=? AND user_id=?',(room['id'],self.a))['role'],'member')
    def test_deactivate_blocks_when_open_order(self):
        p=self.listing();self.checkout([p])  # 买家 b 下单未付款，双方都有未完成订单
        with self.assertRaises(DomainError):self.m.deactivate(self.b)
        with self.assertRaises(DomainError):self.m.deactivate(self.a)
    def test_deactivate_removes_listings_and_blocks_login(self):
        cid=self.login('13800000021');p=self.listing(cid)
        self.m.deactivate(cid)
        self.assertEqual(self.m.product(p)['status'],'removed')
        self.assertEqual(self.m.profile(cid)['status'],'deactivated')
        with self.assertRaises(DomainError):self.login('13800000021')
    def test_ban_blocks_login_and_removes_listings(self):
        cid=self.login('13800000022');p=self.listing(cid)
        self.m.ban_user(self.staff,cid,True,'货不对版且失联')
        self.assertEqual(self.m.profile(cid)['status'],'banned')
        self.assertEqual(self.m.product(p)['status'],'removed')
        with self.assertRaises(DomainError):self.login('13800000022')
        self.m.ban_user(self.staff,cid,False,'核实后解封')
        self.assertEqual(self.m.profile(cid)['status'],'active')
        self.login('13800000022')
    def test_ban_requires_admin_and_cannot_ban_self(self):
        with self.assertRaises(DomainError):self.m.ban_user(self.staff,self.staff,True,'不能封自己')
        cid=self.login('13800000023')
        with self.assertRaises(DomainError):self.m.ban_user(cid,self.a,True,'非管理员不能封')
    def test_reserved_and_sold_products_hidden_from_feed(self):
        p=self.listing();self.assertEqual(len(self.m.products()),1)
        self.checkout([p])  # 下单后商品进入 reserved
        self.assertEqual(len(self.m.products()),0)
        o=self.m.orders(self.b)[0]
        self.m.order_action(self.b,o['id'],'pay',{});self.m.order_action(self.a,o['id'],'deliver',{})
        self.m.order_action(self.b,o['id'],'handover',{});self.m.order_action(self.b,o['id'],'receive',{})
        self.assertEqual(self.m.product(p)['status'],'sold')
        self.assertEqual(len(self.m.products()),0)
    def test_promote_pins_own_available_product(self):
        p1=self.listing(self.a);p2=self.listing(self.a)
        self.assertEqual(self.m.products()[0]['id'],p2)  # 默认最新在前
        self.m.promote(self.a,p1,'7d')
        self.assertEqual(self.m.products()[0]['id'],p1)  # 置顶后 p1 排最前
        with self.assertRaises(DomainError):self.m.promote(self.b,p1,'1d')  # 不能置顶别人的
        with self.assertRaises(DomainError):self.m.promote(self.a,p1,'30d')  # 档位非法
    def test_promote_expires_and_sinks(self):
        p1=self.listing(self.a);p2=self.listing(self.a)
        self.m.promote(self.a,p1,'1d')
        self.assertEqual(self.m.products()[0]['id'],p1)
        with self.m.tx() as c:c.execute('UPDATE products SET promoted_until=0 WHERE id=?',(p1,))  # 到期
        self.assertEqual(self.m.products()[0]['id'],p2)
    def test_want_matches_and_service_fee(self):
        p=self.listing(self.a,title='笔记本电脑 · 轻薄便携')
        w=self.m.create_want(self.b,dict(keyword='电脑',budget=200000,description='想要一台轻薄本'))
        self.assertIn(p,[x['id'] for x in w['matches']])  # 关键词命中
        o=self.m.checkout(self.b,dict(product_ids=[p],delivery='pickup',appointment=time.time()+7200,key='want-check',want_id=w['id']))
        fee=[x for x in o['ledger'] if x['kind']=='service_fee']
        self.assertEqual(fee[0]['amount'],75)  # 1500 分 × 5% = 75 分
        self.assertEqual(self.m.row('SELECT status FROM wants WHERE id=?',(w['id'],))['status'],'matched')
    def test_want_checkout_requires_open(self):
        p=self.listing(self.a,title='笔记本电脑');p2=self.listing(self.a,title='电脑包')
        w=self.m.create_want(self.b,dict(keyword='电脑',budget=200000,description=''))
        self.m.checkout(self.b,dict(product_ids=[p],delivery='pickup',appointment=time.time()+7200,key='w1',want_id=w['id']))
        with self.assertRaises(DomainError):
            self.m.checkout(self.b,dict(product_ids=[p2],delivery='pickup',appointment=time.time()+7200,key='w2',want_id=w['id']))

    def test_refund_locked_product_support_review_and_restore(self):
        """退款冻结的商品：卖家侧锁定原因可见，客服复核申诉后可恢复上架。"""
        p=self.listing();o=self.checkout([p]);oid=o['id']
        self.m.order_action(self.b,oid,'pay',{})
        self.m.order_action(self.a,oid,'deliver',{})
        self.m.order_action(self.b,oid,'handover',{})
        t=self.m.create_ticket(self.b,dict(type='refund',order_id=oid,subject='与描述不符',body='申请退款'))
        self.m.resolve_ticket(self.staff,t['id'],dict(outcome='refund',reason='核实属实，全额退款',amount=o['total']))
        row=[x for x in self.m.my_products(self.a) if x['id']==p][0]
        self.assertEqual(row['status'],'removed')
        self.assertTrue(row['relist_locked']); self.assertIn('客服',row['lock_reason'])
        with self.assertRaises(DomainError):self.m.set_product_status(self.a,p,'relist')
        # 把账号降为普通客服：恢复上架必须客服也能做，否则申诉在客服手里断头
        with self.m.tx() as c:c.execute("UPDATE users SET role='support' WHERE id=?",(self.staff,))
        appeal=self.m.create_ticket(self.a,dict(type='appeal',product_id=p,subject='重新上架复核',body='已与买家协商解决，申请复核'))
        self.m.resolve_ticket(self.staff,appeal['id'],dict(outcome='claim',reason='受理申诉'))
        self.m.moderate_product(self.staff,p,'restore','申诉成立，双方已和解，同意恢复')
        self.assertEqual(self.m.product(p,self.a)['status'],'available')
        # available 商品不携带锁定标志（该标志只在已下架行上出现），状态即可证明解锁
        self.assertNotIn('relist_locked',[x for x in self.m.my_products(self.a) if x['id']==p][0])

    def test_seller_self_delist_relists_freely(self):
        p=self.listing()
        self.m.set_product_status(self.a,p,'delist')
        row=[x for x in self.m.my_products(self.a) if x['id']==p][0]
        self.assertFalse(row['relist_locked'])
        self.m.set_product_status(self.a,p,'relist')
        self.assertEqual(self.m.product(p,self.a)['status'],'available')

    def test_support_room_connects_user_to_desk(self):
        """在线客服：普通用户直达「转角客服」私聊，双方可互发、重复进入同会话。"""
        self.m.create_ticket(self.a,dict(type='other',subject='咨询运费',body='想咨询'))  # 新规则：先提交问题才能进客服会话
        r=self.m.support_room(self.a)
        self.assertEqual(r['kind'],'private'); self.assertEqual(r['name'],'转角客服')
        self.m.send_message(self.a,r['id'],'在吗，想咨询运费','k1')
        desk=self.m.messages(self.staff,r['id'])
        self.assertEqual(desk[0]['body'],'在吗，想咨询运费')
        self.m.send_message(self.staff,r['id'],'您好，请问寄到哪个楼？','k2')
        self.assertEqual(self.m.messages(self.a,r['id'])[-1]['body'],'您好，请问寄到哪个楼？')
        self.assertEqual(self.m.support_room(self.a)['id'],r['id'])

    def test_support_room_claim_prevents_double_pickup(self):
        """客服会话认领：先认领者持有，后来者不抢单；释放后可接手。"""
        self.m.create_ticket(self.a,dict(type='other',subject='咨询',body='想咨询'))
        r=self.m.support_room(self.a)
        with self.m.tx() as c:c.execute("INSERT INTO users(phone,nickname,role,college) VALUES('13800000999','客服B','support','计算机工程学院')")
        s2=self.m.row("SELECT id FROM users WHERE nickname='客服B'")['id']
        c1=self.m.claim_support_room(self.staff,r['id'])
        self.assertTrue(c1['ok']); self.assertEqual(c1['assignee'],self.staff)
        # 客服B 再认领：被拒，返回持有人，不改变 assignee
        c2=self.m.claim_support_room(s2,r['id'])
        self.assertFalse(c2['ok']); self.assertEqual(c2['assignee'],self.staff)
        self.assertEqual(c2['assignee_name'],'转角客服')
        # 释放后客服B 接手成功
        self.m.claim_support_room(self.staff,r['id'],'release')
        c3=self.m.claim_support_room(s2,r['id'])
        self.assertTrue(c3['ok']); self.assertEqual(c3['assignee'],s2)
        # 普通用户不能认领
        with self.assertRaises(DomainError):self.m.claim_support_room(self.a,r['id'])

    def test_support_room_visible_in_staff_pool(self):
        """客服池：未加入的客服也能在 rooms() 里看到待接入的客服会话。"""
        self.m.create_ticket(self.a,dict(type='other',subject='咨询',body='想咨询'))
        r=self.m.support_room(self.a)
        with self.m.tx() as c:c.execute("INSERT INTO users(phone,nickname,role,college) VALUES('13800000998','客服C','support','计算机工程学院')")
        s2=self.m.row("SELECT id FROM users WHERE nickname='客服C'")['id']
        row=[x for x in self.m.rooms(s2)['joined'] if x['id']==r['id']][0]
        self.assertTrue(row.get('via_pool')); self.assertEqual(row['assignee'],0)
        self.assertEqual(row['kind'],'private')

if __name__=='__main__':unittest.main()


class ChatRoomTests(unittest.TestCase):
    """微信风格聊天室：列表摘要、成员接口、消息撤回、首屏取最近一页。"""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.m=Market(self.tmp.name)
        self.a=self.login('13800000021'); self.b=self.login('13800000022')
    def tearDown(self): self.tmp.cleanup()
    def login(self,phone):
        code=self.m.request_code(phone)['demo_code']
        return self.m.login(phone,code)['user']['id']

    def test_room_list_preview_and_unread(self):
        r=self.m.join_room(self.a,'general'); self.m.join_room(self.b,'general')
        self.m.send_message(self.a,r['id'],'大家好啊','k1')
        row=[x for x in self.m.rooms(self.b)['joined'] if x['id']==r['id']][0]
        self.assertEqual(row['last_body'],'大家好啊')
        self.assertEqual(row['last_nick'],self.m.profile(self.a)['nickname'])
        self.assertEqual(row['unread'],1)
        self.m.messages(self.b,r['id'])  # 拉取即已读
        row=[x for x in self.m.rooms(self.b)['joined'] if x['id']==r['id']][0]
        self.assertEqual(row['unread'],0)

    def test_room_members(self):
        r=self.m.join_room(self.a,'general'); self.m.join_room(self.b,'general')
        data=self.m.room_members(self.a,r['id'])
        self.assertEqual(data['room']['kind'],'general')
        self.assertIn(self.a,[m['user_id'] for m in data['members']])
        stranger=self.login('13800000023')
        with self.assertRaises(DomainError):self.m.room_members(stranger,r['id'])

    def test_recall_window_and_permission(self):
        r=self.m.private_room(self.a,self.b)
        befriend(self.m,self.a,self.b)
        self.m.send_message(self.a,r['id'],'说错话了','k1')
        mid=self.m.messages(self.a,r['id'])[0]['id']
        with self.assertRaises(DomainError):self.m.recall_message(self.b,mid)   # 不能撤别人的
        self.m.recall_message(self.a,mid)
        msgs=self.m.messages(self.b,r['id'])
        self.assertEqual(msgs[0]['removed'],2); self.assertEqual(msgs[0]['body'],'')
        with self.assertRaises(DomainError):self.m.recall_message(self.a,mid)   # 已撤回不能再撤
        self.m.send_message(self.a,r['id'],'太久了','k2')
        mid2=self.m.messages(self.a,r['id'],mid)[0]['id']
        with self.m.tx() as c:c.execute('UPDATE messages SET created=? WHERE id=?',(time.time()-180,mid2))
        with self.assertRaises(DomainError):self.m.recall_message(self.a,mid2)  # 超 2 分钟不能撤

    def test_initial_pull_returns_latest_tail(self):
        r=self.m.join_room(self.a,'general')
        for i in range(250):self.m.send_message(self.a,r['id'],'m%d'%i,'k%d'%i)
        first=self.m.messages(self.a,r['id'])
        self.assertEqual(len(first),200)
        self.assertEqual(first[0]['body'],'m50'); self.assertEqual(first[-1]['body'],'m249')
        self.assertEqual(self.m.messages(self.a,r['id'],first[-1]['id']),[])


def befriend(m, a, b):
    """2026-10 起私聊要求先是好友；这里把关系建好，测试才能走到消息逻辑。"""
    m.friend_request(a, b, '')
    incoming = m.friends(b)['incoming']
    if incoming:
        m.friend_decide(b, incoming[0]['id'], True)
