"""信誉分制度（方案 A）测试：扣分表、好评加分、诚信客户标签。

覆盖 docs/信誉分制度方案.md 定稿的规则。最容易漏的两条是防刷：
1) 同一订单重复好评不重复加分；2) 好评加分的日/月上限。

跑法（项目约定：系统 Python 3.8）：
    cd "E:\\zi\\huali-corner-trial"
    "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python38\\python.exe" -m unittest discover -s tests -p "test_credit.py"
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.market import Market, DomainError
from app.account.credit import (
    suggest_penalty, is_trusted, TRUSTED_SCORE,
    AWARD_DAILY_CAP, AWARD_MONTHLY_CAP, AWARD_PER_REVIEW,
)


class CreditRuleTests(unittest.TestCase):
    """纯函数层的规则：扣分公式与门槛。"""

    def test_penalty_escalates_with_price(self):
        # 同一个违规类型，金额越大扣越多；各档基础分正确。
        self.assertEqual(suggest_penalty('minor', 2000), 3 + 0)      # 20 元
        self.assertEqual(suggest_penalty('minor', 5000), 3 + 1)      # 50 元
        self.assertEqual(suggest_penalty('moderate', 15000), 8 + 3)  # 150 元
        self.assertEqual(suggest_penalty('moderate', 30000), 8 + 6)  # 300 元
        self.assertEqual(suggest_penalty('severe', 50000), 15 + 6)   # 500 元

    def test_penalty_tiers_are_inclusive_lower_bound(self):
        # 阶梯「含下不含上」：30 元应落在第二档，不是第一档。
        self.assertEqual(suggest_penalty('minor', 3000), 3 + 1)

    def test_penalty_unknown_violation_raises(self):
        with self.assertRaises(ValueError):
            suggest_penalty('bogus', 1000)

    def test_trusted_threshold(self):
        self.assertTrue(is_trusted(TRUSTED_SCORE))
        self.assertTrue(is_trusted(100))
        self.assertFalse(is_trusted(TRUSTED_SCORE - 1))
        self.assertFalse(is_trusted(0))


class GoodReviewAwardTests(unittest.TestCase):
    """好评自动加分（方案 A 的加分主路径）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.admin = self.m.bootstrap_admin('19065322759', 'adminpass1')['id']
        self.buyer = self.m.register_password('13800000001', 'buyer123', '买家')['user']['id']
        self.seller = self.m.register_password('13800000002', 'seller123', '卖家')['user']['id']
        # 好评 +1 会被 100 分封顶，所以把卖家降到 90，让加分可观测。
        with self.m.tx() as c:
            c.execute('UPDATE users SET score=90 WHERE id=?', (self.seller,))

    def tearDown(self):
        self.tmp.cleanup()

    def order(self, completed=True):
        """造一笔买家↔卖家的订单。"""
        with self.m.tx() as c:
            oid = c.execute(
                "INSERT INTO orders(buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,status,created,completed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (self.buyer, self.seller,
                 json.dumps([{'id': 1, 'title': '测试商品', 'photo': '', 'price': 3000}], ensure_ascii=False),
                 3000, 0, 3000, 'pickup', 'L1',
                 'completed' if completed else 'paid', time.time(), time.time())).lastrowid
        return oid

    def score(self, uid):
        return self.m.profile(uid)['score']

    def test_good_review_awards_ratee(self):
        before = self.score(self.seller)
        self.m.review(self.buyer, self.order(), 5, '很靠谱')
        self.assertEqual(self.score(self.seller), before + AWARD_PER_REVIEW)
        # 留审计（type=credit、actor=0 系统、reason 带好评）
        audit = [a for a in self.m.audit_log(self.admin, limit=100) if a['type'] == 'credit']
        self.assertTrue(any('获得好评' in a['reason'] for a in audit))
        # 通知卖家
        self.assertTrue(any('获得好评' in n['body'] for n in self.m.notifications(self.seller)['items']))

    def test_rerating_same_good_review_does_not_double_award(self):
        oid = self.order()
        self.m.review(self.buyer, oid, 5, '好评')
        after_first = self.score(self.seller)
        self.m.review(self.buyer, oid, 5, '改个措辞')   # 仍是好评
        self.assertEqual(self.score(self.seller), after_first, '重复好评不该重复加分')

    def test_upgrade_from_bad_to_good_awards_once(self):
        oid = self.order()
        self.m.review(self.buyer, oid, 3, '一般')
        mid = self.score(self.seller)
        self.m.review(self.buyer, oid, 5, '改评好评')
        self.assertEqual(self.score(self.seller), mid + AWARD_PER_REVIEW)

    def test_low_rating_does_not_award(self):
        before = self.score(self.seller)
        self.m.review(self.buyer, self.order(), 2, '不满意')
        self.assertEqual(self.score(self.seller), before)

    def test_daily_cap(self):
        before = self.score(self.seller)
        for _ in range(AWARD_DAILY_CAP + 2):        # 造 5 笔订单，超过日上限
            self.m.review(self.buyer, self.order(), 5, '好评')
        self.assertEqual(self.score(self.seller), before + AWARD_DAILY_CAP,
                         '好评加分一天最多 +%d' % AWARD_DAILY_CAP)


class TrustedBadgeTests(unittest.TestCase):
    """诚信客户标签：商品 payload 与主页 flag 按实时分数走。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.seller = self.m.register_password('13800000001', 'seller123', '卖家')['user']['id']

    def tearDown(self):
        self.tmp.cleanup()

    def product(self):
        with self.m.tx() as c:
            return c.execute(
                'INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,status,data,created)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?)',
                (self.seller, '诚信测试商品', 'living', 1000, 0, 'pickup', 'L1', 'available',
                 json.dumps({'description': 'x'}, ensure_ascii=False), time.time())).lastrowid

    def set_score(self, v):
        with self.m.tx() as c:
            c.execute('UPDATE users SET score=? WHERE id=?', (v, self.seller))

    def test_trusted_seller_gets_badge(self):
        self.set_score(95)
        self.assertTrue(self.m.product(self.product())['seller_trusted'])

    def test_below_threshold_loses_badge(self):
        self.set_score(TRUSTED_SCORE - 1)
        self.assertFalse(self.m.product(self.product())['seller_trusted'])


class ViolationSuggestTests(unittest.TestCase):
    """工单页「选违规类型自动算分」（方案 A 最后一公里）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name, trial=True)
        self.admin = self.m.bootstrap_admin('19065322759', 'adminpass1')['id']
        self.seller = self.m.register_password('13800000001', 'seller123', '卖家')['user']['id']
        self.buyer = self.m.register_password('13800000002', 'buyer123', '买家')['user']['id']
        # 商品 + 150 元订单 + 关联工单（report 类型、已结案）
        with self.m.tx() as c:
            pid = c.execute("INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,status,data,created)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (self.seller, '违规商品', 'living', 15000, 0, 'pickup', 'L1', 'available',
                             json.dumps({'description': 'x'}, ensure_ascii=False), time.time())).lastrowid
            oid = c.execute("INSERT INTO orders(buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,status,created)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (self.buyer, self.seller, json.dumps([{'id': pid, 'title': '违规商品', 'photo': '', 'price': 15000}]),
                             15000, 0, 15000, 'pickup', 'L1', 'completed', time.time())).lastrowid
            self.tid = c.execute("INSERT INTO tickets(user_id,order_id,product_id,type,subject,body,status,created)"
                                 " VALUES(?,?,?,?,?,?,?,?)",
                                 (self.buyer, oid, pid, 'report', '货不对板', '详情', 'resolved', time.time())).lastrowid

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_returns_breakdown_without_writing(self):
        before = self.m.profile(self.seller)['score']
        r = self.m.credit_action(self.admin, self.seller, None, '预览', self.tid, 'moderate', dry_run=True)
        # 150 元 → 中度基础 8 + 金额档(100-300)=3 = 11
        self.assertEqual(r['suggested'], 11)
        self.assertEqual(r['base'], 8)
        self.assertEqual(r['extra'], 3)
        self.assertEqual(r['amount'], 15000)
        self.assertEqual(self.m.profile(self.seller)['score'], before, 'dry_run 不应写库')

    def test_violation_auto_applies_suggested_penalty(self):
        before = self.m.profile(self.seller)['score']
        self.m.credit_action(self.admin, self.seller, None, '货不对板，按价格处罚', self.tid, 'moderate')
        self.assertEqual(self.m.profile(self.seller)['score'], before - 11)

    def test_explicit_delta_overrides_suggestion(self):
        before = self.m.profile(self.seller)['score']
        self.m.credit_action(self.admin, self.seller, -5, '人工从轻', self.tid, 'moderate')
        self.assertEqual(self.m.profile(self.seller)['score'], before - 5)


if __name__ == '__main__':
    unittest.main()
