"""缺陷修复回归：对应 docs/功能缺陷清单-2026-10-16.md 的 H2 / H3 / H4 / M1 / M2 / M4 / M5。

每个用例都对应清单里的一条，命名与清单编号对齐，便于后续检索。
运行：python -m unittest discover -s tests -p "test_defect_fixes.py"
"""
import base64, io, json, sys, tempfile, threading, time, unittest, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError
from server import make_server
from PIL import Image


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (80, 80), color).save(buffer, 'PNG')
    return buffer.getvalue()


class DefectFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.seller = self.login('13800000011')
        self.buyer = self.login('13800000012')
        self.admin = self.login('19065322759')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def photos(self, u):
        return [self.m.add_upload(u, png(c), angle)['id']
                for angle, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]

    def listing(self, u=None, **extra):
        u = u or self.seller
        data = dict(title='高等数学 第七版', category='books', price=1500, delivery_fee=300,
                    delivery='both', region='A1楼下', description='实拍教材', photos=self.photos(u),
                    college='计算机工程学院', edition='第七版', publisher='高等教育出版社',
                    condition='有少量笔记', notes='少量', missing='无缺页', accessories='无附件',
                    bought='2024-09', original_price=4500)
        data.update(extra)
        return self.m.publish(u, data)['id']

    def checkout(self, ids, **extra):
        payload = dict(product_ids=ids, delivery='pickup', appointment=time.time() + 7200,
                       key='k-' + str(time.time_ns()))
        payload.update(extra)
        return self.m.checkout(self.buyer, payload)

    def ledger(self, oid):
        return {r['kind']: r['amount'] for r in
                self.m.rows('SELECT kind,amount FROM ledger WHERE order_id=?', (oid,))}

    def want_status(self, wid):
        return self.m.row('SELECT status FROM wants WHERE id=?', (wid,))['status']

    # ---- H2：求购撮合在订单作废时必须回滚 ------------------------------------
    def _matched_want_order(self, **listing_extra):
        p = self.listing(title='笔记本电脑 · 轻薄便携', **listing_extra)
        w = self.m.create_want(self.buyer, dict(keyword='电脑', budget=200000, description=''))
        o = self.checkout([p], want_id=w['id'])
        self.assertEqual(self.want_status(w['id']), 'matched')
        self.assertEqual(self.ledger(o['id'])['service_fee'], 5 * o['subtotal'] // 100)
        return w['id'], o

    def test_H2_cancel_restores_want_and_reverses_fee(self):
        wid, o = self._matched_want_order()
        self.m.order_action(self.buyer, o['id'], 'cancel', {})
        self.assertEqual(self.want_status(wid), 'open')                       # 求购回到可继续匹配
        books = self.ledger(o['id'])
        self.assertEqual(books['service_fee_reversal'], books['service_fee'])  # 服务费已冲销

    def test_H2_timeout_restores_want(self):
        wid, o = self._matched_want_order()
        self.m.tick(time.time() + 1801)                                        # 30 分钟未付款自动关闭
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'cancelled')
        self.assertEqual(self.want_status(wid), 'open')

    def test_H2_refund_restores_want(self):
        wid, o = self._matched_want_order()
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        self.m.order_action(self.seller, o['id'], 'deliver', {})
        self.m.order_action(self.buyer, o['id'], 'handover', {})
        self.m.order_action(self.buyer, o['id'], 'receive', {})
        t = self.m.create_ticket(self.buyer, dict(type='refund', order_id=o['id'],
                                                  subject='缺页', body='实际交付与描述不符'))
        self.m.resolve_ticket(self.admin, t['id'], dict(outcome='refund', reason='核实退款', amount=o['total']))
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'refunded')
        self.assertEqual(self.want_status(wid), 'open')

    def test_H2_edit_order_recomputes_service_fee(self):
        a = self.listing(title='笔记本电脑')
        b = self.listing(title='电脑包')
        w = self.m.create_want(self.buyer, dict(keyword='电脑', budget=200000, description=''))
        o = self.checkout([a, b], want_id=w['id'])
        self.assertEqual(self.ledger(o['id'])['service_fee'], 5 * (1500 + 1500) // 100)
        self.m.update_order(self.buyer, o['id'], dict(product_ids=[a]))
        self.assertEqual(self.ledger(o['id'])['service_fee'], 5 * 1500 // 100)  # 与改单后的小计一致

    # ---- H4：卖家 24 小时确认窗口从付款时间起算 -------------------------------
    def test_H4_confirmation_window_counts_from_paid_at(self):
        o = self.checkout([self.listing()])
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        now = time.time()
        with self.m.tx() as c:      # 下单 24 小时前，但 60 秒前才付款
            c.execute("UPDATE orders SET created=?,paid_at=? WHERE id=?", (now - 86401, now - 60, o['id']))
        self.m.tick(now)
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'paid')   # 不该被自动退款

    def test_H4_overdue_confirmation_still_refunds(self):
        o = self.checkout([self.listing()])
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        now = time.time()
        with self.m.tx() as c:
            c.execute("UPDATE orders SET created=?,paid_at=? WHERE id=?", (now - 90000, now - 86401, o['id']))
        self.m.tick(now)
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'cancelled')
        self.assertEqual(self.ledger(o['id'])['refund'], o['total'])

    # ---- M4：封禁账号必须处理在途订单 ----------------------------------------
    def test_M4_ban_seller_moves_paid_order_to_dispute_with_ticket(self):
        o = self.checkout([self.listing()])
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        self.m.ban_user(self.admin, self.seller, True, '货不对版且失联')
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'disputed')
        ticket = self.m.row("SELECT * FROM tickets WHERE order_id=? AND type='refund'", (o['id'],))
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket['user_id'], self.buyer)                          # 替买家建档，买家不必自己摸索入口
        self.assertEqual(ticket['status'], 'open')

    def test_M4_ban_cancels_unpaid_order_and_releases_product(self):
        p = self.listing()
        w = self.m.create_want(self.buyer, dict(keyword='高等数学', budget=200000, description=''))
        o = self.checkout([p], want_id=w['id'])
        self.m.ban_user(self.admin, self.seller, True, '重复违规发布')
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'cancelled')
        # F-01：商品必须保持 removed —— 旧实现在这里复活成 available，被封卖家
        # 的商品重新进入公开列表，其他买家仍可下单（QA 复现）。
        self.assertEqual(self.m.row('SELECT status FROM products WHERE id=?', (p,))['status'], 'removed')
        self.assertEqual(self.want_status(w['id']), 'open')

    def test_M4_unban_only_applies_to_banned_account(self):
        with self.assertRaises(DomainError):
            self.m.ban_user(self.admin, self.seller, False, '本来就没封')
        self.m.ban_user(self.admin, self.seller, True, '封禁')
        self.m.ban_user(self.admin, self.seller, False, '核实后解封')
        self.assertEqual(self.m.profile(self.seller)['status'], 'active')

    # ---- M5：站内通知 --------------------------------------------------------
    def test_M5_order_events_notify_counterpart(self):
        o = self.checkout([self.listing()])
        self.assertIn('order_created', [n['kind'] for n in self.m.notifications(self.seller)['items']])
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        self.assertIn('order_paid', [n['kind'] for n in self.m.notifications(self.seller)['items']])
        self.m.order_action(self.seller, o['id'], 'deliver', {})
        self.assertIn('order_delivered', [n['kind'] for n in self.m.notifications(self.buyer)['items']])

    def test_M5_unread_count_and_mark_all_read(self):
        self.checkout([self.listing()])
        self.assertEqual(self.m.notifications(self.seller)['unread'], 1)
        self.m.read_notifications(self.seller)
        self.assertEqual(self.m.notifications(self.seller)['unread'], 0)
        self.m.order_action(self.buyer, self.m.orders(self.buyer)[0]['id'], 'pay', {})
        self.assertEqual(self.m.notifications(self.seller)['unread'], 1)

    def test_M5_ticket_reply_and_resolution_notify_user(self):
        t = self.m.create_ticket(self.buyer, dict(type='other', subject='咨询', body='请问怎么取消订单'))
        self.m.reply_ticket(self.admin, t['id'], dict(body='在订单页点取消即可', internal=False))
        self.assertIn('ticket_reply', [n['kind'] for n in self.m.notifications(self.buyer)['items']])
        self.m.resolve_ticket(self.admin, t['id'], dict(outcome='resolved', reason='已答复'))
        self.assertIn('ticket_resolved', [n['kind'] for n in self.m.notifications(self.buyer)['items']])

    def test_M5_internal_note_does_not_notify(self):
        t = self.m.create_ticket(self.buyer, dict(type='other', subject='咨询', body='内容'))
        before = self.m.notifications(self.buyer)['unread']
        self.m.reply_ticket(self.admin, t['id'], dict(body='内部备注', internal=True))
        self.assertEqual(self.m.notifications(self.buyer)['unread'], before)

    # ---- 商品状态与置顶的一致性 ----------------------------------------------
    def test_relist_blocked_after_refund_until_reviewed(self):
        p = self.listing()
        o = self.checkout([p])
        self.m.order_action(self.buyer, o['id'], 'pay', {})
        t = self.m.create_ticket(self.buyer, dict(type='refund', order_id=o['id'], subject='仅退款', body='物品留在买家处'))
        self.m.resolve_ticket(self.admin, t['id'], dict(outcome='refund', reason='核实仅退款', amount=o['total']))
        with self.assertRaises(DomainError):
            self.m.set_product_status(self.seller, p, 'relist')   # 需求 §10.6：物品不在卖家手里，不能自行恢复出售

    def test_delist_clears_unexpired_promotion(self):
        p = self.listing()
        self.m.promote(self.seller, p, '7d')
        self.m.set_product_status(self.seller, p, 'delist')
        self.m.set_product_status(self.seller, p, 'relist')
        self.assertEqual(self.m.row('SELECT promoted_until FROM products WHERE id=?', (p,))['promoted_until'], 0)

    def test_relist_requires_minimum_score(self):
        p = self.listing()
        self.m.set_product_status(self.seller, p, 'delist')
        with self.m.tx() as c:
            c.execute('UPDATE users SET score=50 WHERE id=?', (self.seller,))
        with self.assertRaises(DomainError):
            self.m.set_product_status(self.seller, p, 'relist')

    def test_expired_sessions_are_cleaned_by_tick(self):
        with self.m.tx() as c:
            c.execute('INSERT INTO sessions VALUES(?,?,?)', ('deadbeef', self.buyer, time.time() - 10))
        self.m.tick(time.time())
        self.assertIsNone(self.m.row('SELECT 1 FROM sessions WHERE token=?', ('deadbeef',)))


class MediaSnapshotTests(unittest.TestCase):
    """H3：商品被下架/退款/封禁后，订单快照引用的商品图不能再变成 403 裂图。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(self.tmp.name, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.market = self.server.market
        self.seller = self.login('13800000001')
        self.buyer = self.login('13800000002')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def login(self, phone):
        code = self.market.request_code(phone)['demo_code']
        return self.market.login(phone, code)['token']

    def req(self, path, data=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    self.base + path, data=json.dumps(data).encode() if data is not None else None,
                    headers=headers)) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_H3_order_snapshot_photo_survives_product_removal(self):
        uploads = [self.market.add_upload(self.market.user(self.seller), png(c), a)['id']
                   for a, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]
        pid = self.market.publish(self.market.user(self.seller), dict(
            title='高等数学 第七版', category='books', price=1500, delivery_fee=0, delivery='pickup',
            region='A1楼下', description='实拍教材', photos=uploads, college='计算机工程学院',
            edition='第七版', publisher='高等教育出版社', condition='有少量笔记', notes='少量',
            missing='无缺页', accessories='无附件', bought='2024-09', original_price=4500))['id']
        self.market.checkout(self.market.user(self.buyer), dict(
            product_ids=[pid], delivery='pickup', address='', appointment=time.time() + 7200, key='media-test'))
        photo = '/media/' + uploads[0]
        self.assertEqual(self.req(photo, token=self.buyer)[0], 200)          # 在售时公开
        with self.market.tx() as c:                                         # 模拟退款/封禁后的下架
            c.execute("UPDATE products SET status='removed' WHERE id=?", (pid,))
        self.assertEqual(self.req(photo, token=self.buyer)[0], 200)          # 订单快照仍要能显示
        stranger = self.market.add_upload(self.market.user(self.seller), png('yellow'), 'extra')['id']
        self.assertEqual(self.req('/media/' + stranger, token=self.buyer)[0], 403)  # 未发布的图继续拦截


class F01BannedSellerReleaseTests(unittest.TestCase):
    """F-01：卖家被封禁后，取消其待付款订单时 release() 又把商品设为
    available，商品重新进入公开列表，其他买家仍可下单。

    修复口径：
      · release() 只解锁 reserved 商品，卖家 banned/deleted 时置 removed；
      · 公开商品流只展示 active 卖家的商品；
      · checkout() 校验卖家 status='active'（数据库中残留的 available 脏数据也拦得住）。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.admin = self.m.bootstrap_admin('19065322759', 'adminpass1')['id']
        self.seller = self.m.register_password('13800000041', 'seller123', '卖家')['user']['id']
        self.buyer = self.m.register_password('13800000042', 'buyer123', '买家')['user']['id']

    def tearDown(self):
        self.tmp.cleanup()

    def listing(self, u=None, **extra):
        u = u or self.seller
        data = dict(title='高等数学 第七版', category='books', price=1500, delivery_fee=300,
                    delivery='both', region='A1楼下', description='实拍教材', photos=self.photos(u),
                    college='计算机工程学院', edition='第七版', publisher='高等教育出版社',
                    condition='有少量笔记', notes='少量', missing='无缺页', accessories='无附件',
                    bought='2024-09', original_price=4500)
        data.update(extra)
        return self.m.publish(u, data)['id']

    def photos(self, u):
        return [self.m.add_upload(u, png(c), angle)['id']
                for angle, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]

    def checkout(self, ids, want=None, **extra):
        payload = dict(product_ids=ids, delivery='pickup', appointment=time.time() + 7200,
                       key='k-' + str(time.time_ns()))
        if want is not None:
            payload['want_id'] = want
        payload.update(extra)
        return self.m.checkout(self.buyer, payload)

    def test_banned_seller_product_stays_out_of_public_feed(self):
        p = self.listing()
        self.assertEqual(len(self.m.products()), 1)
        self.checkout([p])                                    # 商品进入 reserved，挂在待付款订单上
        self.m.ban_user(self.admin, self.seller, True, '引流违规')
        self.assertEqual(self.m.row('SELECT status FROM products WHERE id=?', (p,))['status'], 'removed')
        self.assertEqual(self.m.products(), [])               # 公开列表不得出现被封卖家的商品

    def test_banned_seller_product_cannot_be_checked_out(self):
        """数据库里残留的 available 脏数据（历史 bug 造成或手工改的）也要被拦住。"""
        p = self.listing()
        self.m.ban_user(self.admin, self.seller, True, '引流违规')
        with self.m.tx() as c:                                # 模拟历史脏数据：商品还是 available
            c.execute("UPDATE products SET status='available' WHERE id=?", (p,))
        with self.assertRaises(DomainError) as ctx:
            self.checkout([p])
        self.assertEqual(ctx.exception.status, 409)
        self.assertIn('卖家', str(ctx.exception))

    def test_buyer_banned_own_unpaid_order_keeps_seller_product_selling(self):
        """买家被封只应取消自己的订单；卖家的正常商品继续在售（不能被误伤）。"""
        p = self.listing()
        self.checkout([p])
        self.m.ban_user(self.admin, self.buyer, True, '恶意占单')
        self.assertEqual(self.m.row('SELECT status FROM products WHERE id=?', (p,))['status'], 'available')
        self.assertEqual(len(self.m.products()), 1)

    def test_timeout_cancel_still_returns_product_to_feed(self):
        """正常路径不回归：无人认领的待付款订单 30 分钟超时关闭后商品回到在售。"""
        p = self.listing()
        o = self.checkout([p])
        self.m.tick(time.time() + 1801)
        self.assertEqual(self.m.order(self.buyer, o['id'])['status'], 'cancelled')
        self.assertEqual(self.m.row('SELECT status FROM products WHERE id=?', (p,))['status'], 'available')

    def test_unban_does_not_silently_relist(self):
        """解封只恢复登录能力；商品恢复上架是卖家/客服的显式动作，且 delisted_by 归属不变。"""
        p = self.listing()
        self.m.ban_user(self.admin, self.seller, True, '误封')
        self.m.ban_user(self.admin, self.seller, False, '核实后解封')
        self.assertEqual(self.m.profile(self.seller)['status'], 'active')
        self.assertEqual(self.m.row('SELECT status FROM products WHERE id=?', (p,))['status'], 'removed')
        self.assertEqual(self.m.products(), [])


if __name__ == '__main__':
    unittest.main()
