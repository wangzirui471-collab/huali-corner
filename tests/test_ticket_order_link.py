"""工单交易凭证回归：举报自动关联订单、客服补关联、候选订单列表。

背景：举报工单从商品页发起时只带 product_id，处理人打开工单看到的是
「未关联订单」，既看不到金额也无法判断责任。这里的用例锁住三条行为：
  1. 提交人买过该商品 → 提交时自动挂上最近一笔订单；
  2. 提交人没买过（举报别人的商品）→ 允许无订单，不拦提交；
  3. 历史工单 → 客服可从当事人订单里补关联，且只允许相关订单。

运行：
    cd "E:\\zi\\huali-corner-trial"
    "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python38\\python.exe" -m unittest tests.test_ticket_order_link
"""
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError
from PIL import Image


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (80, 80), color).save(buffer, 'PNG')
    return buffer.getvalue()


class TicketOrderLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.seller = self.login('13800000011')
        self.buyer = self.login('13800000012')
        self.other = self.login('13800000013')
        self.admin = self.login('19065322759')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        return self.m.login(phone, self.m.request_code(phone)['demo_code'])['user']['id']

    def photos(self, u):
        return [self.m.add_upload(u, png(c), angle)['id']
                for angle, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]

    def listing(self, u=None, title='倍思耳机'):
        u = u or self.seller
        return self.m.publish(u, dict(
            title=title, category='living', price=2000, delivery_fee=0,
            delivery='pickup', region='D6 楼下', description='实拍',
            photos=self.photos(u)))['id']

    def checkout(self, uid, pid):
        return self.m.checkout(uid, dict(
            product_ids=[pid], delivery='pickup',
            appointment=time.time() + 3600, key='k-' + str(time.time_ns())))

    def test_report_auto_links_buyer_order(self):
        """买家举报自己买过的商品：工单自动带上那笔订单。"""
        pid = self.listing()
        order = self.checkout(self.buyer, pid)
        t = self.m.create_ticket(self.buyer, dict(
            type='report', product_id=pid, subject='假货', body='收到的耳机是仿品'))
        self.assertEqual(t['order_id'], order['id'])
        self.assertEqual(t['product_id'], pid)

    def test_report_without_purchase_stays_unlinked(self):
        """举报别人的商品、自己没交易过：允许无订单，不能硬塞别人的订单。"""
        pid = self.listing()
        self.checkout(self.buyer, pid)          # 买家买过
        # other 没买过，举报同一件商品
        t = self.m.create_ticket(self.other, dict(
            type='report', product_id=pid, subject='疑似假货', body='看图片不像正品'))
        self.assertIsNone(t['order_id'])

    def test_manual_order_must_match_ticket_product(self):
        """手填订单号但不含该商品：拒绝，避免工单挂着错误的交易。"""
        pid = self.listing()
        other_pid = self.listing(title='小风扇')
        order = self.checkout(self.buyer, other_pid)
        with self.assertRaises(DomainError):
            self.m.create_ticket(self.buyer, dict(
                type='report', product_id=pid, order_id=order['id'],
                subject='假货', body='订单对不上商品'))

    def test_staff_links_legacy_ticket(self):
        """历史工单（提交时还没有订单）：客服可补关联。"""
        pid = self.listing()
        t = self.m.create_ticket(self.buyer, dict(
            type='report', product_id=pid, subject='假货', body='先提交，后下单'))
        self.assertIsNone(t['order_id'])
        order = self.checkout(self.buyer, pid)

        candidates = self.m.ticket_order_candidates(self.admin, t['id'])
        self.assertTrue(any(c['id'] == order['id'] and c['matched_product'] for c in candidates),
                        '候选里应把这笔含涉事商品的订单排在前面并标记')

        linked = self.m.link_ticket_order(self.admin, t['id'], order['id'])
        self.assertEqual(linked['order_id'], order['id'])
        audit = [a for a in self.m.audit_log(self.admin, limit=50) if a['type'] == 'ticket_link_order']
        self.assertTrue(audit, '补关联必须留审计')

    def test_link_rejects_unrelated_order(self):
        """与工单当事人无关的订单不能绑上来。"""
        pid = self.listing()
        t = self.m.create_ticket(self.buyer, dict(
            type='report', product_id=pid, subject='假货', body='无订单'))
        other_pid = self.listing(title='别人的东西')
        stranger_order = self.checkout(self.other, other_pid)
        with self.assertRaises(DomainError):
            self.m.link_ticket_order(self.admin, t['id'], stranger_order['id'])

    def test_link_requires_staff(self):
        """普通用户不能给自己或他人工单改绑订单。"""
        pid = self.listing()
        t = self.m.create_ticket(self.buyer, dict(
            type='report', product_id=pid, subject='假货', body='无订单'))
        with self.assertRaises(DomainError):
            self.m.link_ticket_order(self.buyer, t['id'], 1)

    def test_refund_still_requires_order(self):
        """退款工单不允许无订单——这条不能被自动关联的改动放松。"""
        with self.assertRaises(DomainError):
            self.m.create_ticket(self.buyer, dict(
                type='refund', subject='要退款', body='没有订单也要退'))

    def test_candidates_only_include_related_orders(self):
        """候选列表不能把全平台订单都端给客服。"""
        pid = self.listing()
        t = self.m.create_ticket(self.buyer, dict(
            type='report', product_id=pid, subject='假货', body='无订单'))
        mine = self.checkout(self.buyer, pid)
        other_pid = self.listing(title='无关商品')
        stranger = self.checkout(self.other, other_pid)
        ids = [c['id'] for c in self.m.ticket_order_candidates(self.admin, t['id'])]
        self.assertIn(mine['id'], ids)
        self.assertNotIn(stranger['id'], ids)


if __name__ == '__main__':
    unittest.main()
