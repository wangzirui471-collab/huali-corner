"""违禁品自动审核 + 反引流检测的规则引擎测试。

跑法（项目约定：必须用系统 Python 3.8，它装了 PIL）：
    cd "E:\\zi\\huali-corner-trial"
    "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python38\\python.exe" -m unittest discover -s tests -p "test_moderation.py"
"""
import sys
import tempfile
import unittest
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app import moderation
from app.moderation.rules import RANK
from app.market import Market, DomainError
from PIL import Image


class RuleSetTests(unittest.TestCase):
    def setUp(self):
        self.r = moderation.rules()

    # --- 词表本身 ---------------------------------------------------------

    def test_wordlist_is_loaded_and_not_empty(self):
        self.assertGreater(len(self.r), 200, '词表没加载进来')

    def test_no_single_char_entries_survive(self):
        """单字词条必须被拒收——「刀」收了，「剪刀」「水果刀」「<刀锋>」全部误伤。"""
        for item in self.r.words:
            self.assertGreaterEqual(len(item['word']), 2, f'单字词条漏进来了: {item["word"]}')

    def test_skipped_entries_are_explained(self):
        for source, word, reason in self.r.skipped:
            self.assertTrue(source.endswith('.txt') and word and reason)

    def test_every_entry_has_known_action(self):
        for item in self.r.words:
            self.assertIn(item['action'], RANK, item)

    # --- 正常内容不能误伤 -------------------------------------------------

    def test_normal_listing_passes(self):
        report = self.r.scan('计算机网络 谢希仁 第八版 高等教育出版社，有少量笔记，无缺页')
        self.assertEqual(report['action'], 'ok', report['hits'])

    def test_scissors_and_book_title_are_not_flagged(self):
        for text in ('剪刀一把，文具用', '《刀锋》毛姆 正版', '美工刀片一盒'):
            self.assertEqual(self.r.scan(text)['action'], 'ok', text)

    def test_yard_and_building_codes_are_not_flagged(self):
        self.assertEqual(self.r.scan('A1楼下 L17 G4主楼 自提')['action'], 'ok')

    # --- 违禁品 -----------------------------------------------------------

    def test_controlled_blade_is_blocked(self):
        report = self.r.scan('出售全新未拆匕首，需要的私信')
        self.assertTrue(report['blocked'])
        self.assertIn('管制刀具', [h['category'] for h in report['hits']])

    def test_condom_is_reviewed_not_blocked(self):
        """避孕套是「平台限制」不是法定违禁，只转人工审核，不拦死。"""
        report = self.r.scan('避孕套 未拆封 3只装')
        self.assertFalse(report['blocked'])
        self.assertEqual(report['action'], 'review')

    def test_dorm_appliance_is_reviewed(self):
        report = self.r.scan('出个二手电饭锅，宿舍想换大的')
        self.assertEqual(report['action'], 'review')

    def test_academic_misconduct_is_blocked(self):
        self.assertTrue(self.r.scan('代写论文 包过 诚信经营')['blocked'])

    # --- 反引流 -----------------------------------------------------------

    def test_adding_wechat_is_blocked(self):
        report = self.r.scan('书还在，加微信详聊')
        self.assertTrue(report['blocked'])
        self.assertIn('加微信', [h['hit'] for h in report['hits']])

    def test_external_link_is_blocked(self):
        self.assertTrue(self.r.scan('详见 http://taobao.com/item?id=1')['blocked'])
        self.assertTrue(self.r.scan('看图 www.abc.com')['blocked'])

    def test_bare_phone_number_is_only_reviewed(self):
        """光写一串号码是「疑似」，够不上拦截——真正的拦截交给「加微信」这类指令词。"""
        report = self.r.scan('联系 13800138000')
        self.assertEqual(report['action'], 'review')

    def test_offline_meetup_is_allowed(self):
        """「当面交易」在本站是正常交付方式，不能因为反引流被误杀。"""
        self.assertEqual(self.r.scan('支持当面交易，A1楼下自提')['action'], 'ok')

    def test_isbn_is_not_mistaken_for_a_qq_number(self):
        report = moderation.scan_product({'title': '计算机网络', 'isbn': '9787040254605'})
        self.assertEqual(report['action'], 'ok', report['hits'])

    # --- 判定合并 ---------------------------------------------------------

    def test_worst_level_wins(self):
        report = self.r.scan('避孕套 未拆封；另外加微信详聊')
        self.assertTrue(report['blocked'], '一段文本里同时有中危和高危时应取高危')

    def test_overlapping_hits_are_reported_once(self):
        hits = self.r.scan('打 13800138000')['hits']
        numbers = [h for h in hits if h['hit'] == '13800138000']
        self.assertEqual(len(numbers), 1, '同一串号码被两条正则重复报了')

    def test_covered_weaker_hit_is_dropped(self):
        """「走闲鱼」命中后，里面包的「闲鱼」不该再单独列出来当理由。"""
        hits = self.r.scan('走闲鱼交易')['hits']
        self.assertNotIn('闲鱼', [h['hit'] for h in hits])

    def test_empty_and_blank_text_is_safe(self):
        for text in ('', None, '   ', '\n'):
            self.assertEqual(self.r.scan(text)['action'], 'ok')

    def test_long_text_does_not_crash(self):
        self.assertEqual(self.r.scan('同学好' * 5000)['action'], 'ok')

    # --- 商品扫描与提示文案 ------------------------------------------------

    def test_scan_product_merges_fields(self):
        report = moderation.scan_product({'title': '高等数学', 'description': '加微信 XYZ 便宜出'})
        self.assertTrue(report['blocked'])

    def test_scan_product_handles_missing_fields(self):
        self.assertEqual(moderation.scan_product({})['action'], 'ok')
        self.assertEqual(moderation.scan_product(None)['action'], 'ok')

    def test_message_names_the_hit_but_not_the_whole_wordlist(self):
        report = self.r.scan('出售雷管')
        message = moderation.message_for(report)
        self.assertIn('雷管', message)
        self.assertLess(len(message), 200, '提示不该把整份词表倒出来')

    def test_report_of_is_compact_and_json_safe(self):
        import json
        report = moderation.report_of(self.r.scan('避孕套 未拆封'))
        self.assertEqual(report['action'], 'review')
        self.assertFalse(report['reviewed'])
        json.dumps(report, ensure_ascii=False)

    def test_report_of_returns_none_when_clean(self):
        self.assertIsNone(moderation.report_of(self.r.scan('高等数学 第七版')))


class PublishIntegrationTests(unittest.TestCase):
    """发布链路端到端：确认审核真的接在 publish 上，而不只是一个孤立模块。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Market(self.tmp.name)
        self.seller = self.login('13800000021')
        self.buyer = self.login('13800000022')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, phone):
        code = self.m.request_code(phone)['demo_code']
        return self.m.login(phone, code)['user']['id']

    def photos(self, u):
        ids = []
        for angle, color in zip(['front', 'side', 'top'], ['red', 'green', 'blue']):
            buf = io.BytesIO()
            Image.new('RGB', (100, 100), color).save(buf, 'PNG')
            ids.append(self.m.add_upload(u, buf.getvalue(), angle)['id'])
        return ids

    def payload(self, **extra):
        data = dict(title='高等数学 第七版', category='books', price=1500, delivery_fee=300,
                    delivery='both', region='A1楼下', description='实拍教材',
                    photos=self.photos(self.seller), college='计算机工程学院',
                    edition='第七版', publisher='高等教育出版社', condition='有少量笔记',
                    notes='少量', missing='无缺页', accessories='无附件',
                    bought='2024-09', original_price=4500)
        data.update(extra)
        return data

    def test_banned_item_is_refused_at_publish(self):
        with self.assertRaises(DomainError) as ctx:
            self.m.publish(self.seller, self.payload(title='全新未开刃匕首 便宜出'))
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn('匕首', str(ctx.exception))

    def test_diversion_attempt_is_refused_at_publish(self):
        with self.assertRaises(DomainError):
            self.m.publish(self.seller, self.payload(description='书还在，加微信 abc 详聊'))

    def test_restricted_item_publishes_but_is_marked_for_review(self):
        pid = self.m.publish(self.seller, self.payload(title='未拆封避孕套 3只装'))['id']
        own = self.m.product(pid, self.seller)
        self.assertTrue(own['under_review'])
        self.assertEqual(own['moderation']['action'], 'review')
        self.assertFalse(own['moderation']['reviewed'])

    def test_hit_words_are_not_exposed_to_other_users(self):
        """命中词只有卖家和工作台能看；公开出去等于给出「哪个词会触发审核」的答案。"""
        pid = self.m.publish(self.seller, self.payload(title='未拆封避孕套 3只装'))['id']
        public = self.m.product(pid, self.buyer)
        self.assertTrue(public['under_review'])
        self.assertNotIn('moderation', public)
        self.assertNotIn('避孕套', str(public.get('moderation', '')))

    def test_clean_product_carries_no_marker(self):
        pid = self.m.publish(self.seller, self.payload())['id']
        own = self.m.product(pid, self.seller)
        self.assertFalse(own['under_review'])
        self.assertNotIn('moderation', own)

    def test_review_marked_product_still_shows_in_feed(self):
        """中危是「放行但打标」，不是下架 —— 商品必须照常出现在商品流里。"""
        pid = self.m.publish(self.seller, self.payload(title='未拆封避孕套 3只装'))['id']
        self.assertIn(pid, [p['id'] for p in self.m.products(self.buyer)])


if __name__ == '__main__':
    unittest.main()
