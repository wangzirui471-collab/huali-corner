"""管理员调整星级的规则：能调、调得对、越权与非法值被拒、记录可见。"""
import unittest, tempfile, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError


class CreditStarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.admin = self.login('19065322759')
        self.a = self.login('13800000011')   # 普通卖家
        self.b = self.login('13800000012')   # 普通买家

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        code = self.m.request_code(phone)['demo_code']
        return self.m.login(phone, code)['user']['id']

    def test_admin_can_adjust_stars_and_cap(self):
        self.assertEqual(self.m.profile(self.a)['stars'], 4)          # 4 星起步
        self.assertEqual(self.m.adjust_stars(self.admin, self.a, 2, '毕业季优质卖家')['stars'], 6)
        self.assertEqual(self.m.profile(self.a)['stars'], 6)          # 落到了资料上
        self.assertEqual(self.m.adjust_stars(self.admin, self.a, 2, '继续奖励')['stars'], 7)  # 封顶 7
        self.assertEqual(self.m.adjust_stars(self.admin, self.a, -2, '回收部分奖励')['stars'], 5)
        self.assertEqual(self.m.adjust_stars(self.admin, self.a, -2, '持续违规')['stars'], 3)

    def test_adjust_stars_rejects_abuse(self):
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.a, self.b, 1, '普通用户不能调')   # 非管理员
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.admin, self.admin, 1, '不能调自己')
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.admin, self.a, 3, '超出单次范围')
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.admin, self.a, 0, '不能为 0')
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.admin, self.a, 1, '')            # 必须写理由

    def test_adjustment_visible_in_history(self):
        self.m.adjust_stars(self.admin, self.a, 1, '误判纠正')
        history = self.m.credit_history(self.a)
        stars = [x for x in history if x['kind'] == 'stars']
        self.assertEqual(len(stars), 1)
        self.assertEqual(stars[0]['delta'], 1)
        self.assertIn('误判纠正', stars[0]['reason'])

    def test_admin_stars_not_adjustable_by_others(self):
        # 另一个管理员也不能改 admin 的星级（防管理员互斗）
        with self.assertRaises(DomainError):
            self.m.adjust_stars(self.admin, self.admin, -1, '不能降管理员')


if __name__ == '__main__':
    unittest.main()
