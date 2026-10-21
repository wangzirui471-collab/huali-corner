import unittest
from pathlib import Path
from types import SimpleNamespace

import cloudflare_test_support  # noqa: F401 - 设置 sys.path 并桩掉 workers

import app.cloudflare.ai_support as ai


class AiSupportTests(unittest.IsolatedAsyncioTestCase):
    def test_greeting_with_question_is_business(self):
        # 「你好，怎么退款」不能被当成纯问候
        self.assertEqual(ai.classify('你好，怎么退款'), 'business')
        self.assertEqual(ai.classify('你好'), 'greeting')
        self.assertEqual(ai.classify('谢谢'), 'greeting')

    def test_process_question_not_transferred(self):
        # 流程咨询和投诉都按业务问题处理；只有明说「转人工」才升级（ChatterMate 模式）
        self.assertEqual(ai.classify('怎么退钱'), 'business')
        self.assertEqual(ai.classify('退款要多久'), 'business')
        self.assertEqual(ai.classify('我要投诉'), 'business')
        self.assertEqual(ai.classify('怎么投诉'), 'business')
        self.assertEqual(ai.classify('我要转人工'), 'human')
        self.assertEqual(ai.classify('找客服'), 'human')

    async def test_complaint_is_not_auto_escalated(self):
        # 对处理结果不满：先接住情绪 + 给自助路径，不替客户升级
        r = await ai.ai_answer('你们这平台骗子，我要投诉', SimpleNamespace())
        self.assertEqual(r['action'], 'reply')
        self.assertIn('抱歉', r['answer'])

    async def test_human_intent_transfers_online_and_leaves_message_offline(self):
        original = ai.support_state
        try:
            ai.support_state = lambda now=None: {'online': True, 'hours': '08:00—20:00', 'next_open': '今天 08:00'}
            r = await ai.ai_answer('我要转人工', SimpleNamespace())
            self.assertEqual(r['action'], 'transfer')
            ai.support_state = lambda now=None: {'online': False, 'hours': '08:00—20:00', 'next_open': '明天 08:00'}
            r2 = await ai.ai_answer('我要转人工', SimpleNamespace())
            self.assertEqual(r2['action'], 'leave_message')
            self.assertIn('不在线', r2['answer'])
        finally:
            ai.support_state = original

    def test_links(self):
        self.assertEqual(ai.links_for('怎么发布闲置')[0]['href'], '#publish')
        self.assertIn('#orders', [l['href'] for l in ai.links_for('怎么取消订单、怎么退款')])
        self.assertEqual(ai.links_for('怎么注销账号')[0]['href'], '#me')
        self.assertEqual(ai.links_for('客服什么时候在线、怎么找人工')[0]['href'], '#support')

    def _memory_db(self):
        import sqlite3
        from cloudflare_test_support import Binding
        from app.cloudflare.d1 import Database
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        root = Path(cloudflare_test_support.__file__).resolve().parents[1]
        conn.executescript((root / 'Backend mission/app/cloudflare/schema.sql').read_text(encoding='utf-8'))
        self.addCleanup(conn.close)
        conn.execute("INSERT INTO users(id,phone,nickname) VALUES(1,'13800000001','卖家')")
        return Database(Binding(conn))

    async def test_buy_query_derives_keywords_from_catalog(self):
        ai._CATALOG['at'] = 0.0
        db = self._memory_db()
        await db.run("INSERT INTO products(id,seller_id,title,category,price,status,data,created) "
                     "VALUES(1,1,'青轴机械键盘','electronics',19900,'available','{}',1)")
        # 「一个」不在目录里会被丢掉，只留「键盘」
        self.assertEqual(await ai.buy_query('我想买一个键盘', db), '键盘')
        # 目录里没有的词也保留，让搜索去跑一遍再报没找到
        self.assertEqual(await ai.buy_query('有没有台灯', db), '台灯')
        self.assertIsNone(await ai.buy_query('怎么发布闲置', db))
        self.assertIsNone(await ai.buy_query('我要投诉', db))

    async def test_buy_search_ranks_title_matches_first(self):
        db = self._memory_db()
        await db.run("INSERT INTO products(id,seller_id,title,category,price,status,data,created) "
                     "VALUES(1,1,'键帽收纳盒','electronics',9900,'available','{\"description\":\"适用于键盘\"}',1)")
        await db.run("INSERT INTO products(id,seller_id,title,category,price,status,data,created) "
                     "VALUES(2,1,'罗技机械键盘 K380','electronics',29900,'available','{}',2)")
        rows = await ai.buy_search(db, '键盘')
        self.assertEqual(rows[0]['title'], '罗技机械键盘 K380')
        self.assertEqual(len(rows), 2)

    async def test_buy_answer_returns_products_and_search_link(self):
        db = self._memory_db()
        await db.run("INSERT INTO products(id,seller_id,title,category,price,status,data,created) "
                     "VALUES(1,1,'青轴机械键盘','electronics',19900,'available',"
                     "'{\"photos\":[{\"url\":\"/media/pic1\"}]}',1)")
        r = await ai.buy_answer(db, '键盘')
        self.assertEqual(len(r['products']), 1)
        self.assertEqual(r['products'][0]['title'], '青轴机械键盘')
        self.assertEqual(r['products'][0]['url'], '/media/pic1')
        self.assertEqual(r['links'][0]['action'], 'pet-search')
        self.assertEqual(r['links'][0]['q'], '键盘')

    async def test_api_failure_degrades_instead_of_raising(self):
        original = ai.call_api

        async def boom(*a, **k):
            raise RuntimeError('DeepSeek 401')

        ai.call_api = boom
        try:
            r = await ai.ai_answer('怎么发布闲置', SimpleNamespace())
        finally:
            ai.call_api = original
        self.assertEqual(r['mode'], 'mock')
        self.assertTrue(r['answer'])
        self.assertIn('#publish', [l['href'] for l in r['links']])

    async def test_history_is_passed_to_model(self):
        captured = {}
        original = ai.call_api

        async def fake(q, ctx, env, history=None):
            captured['history'] = history
            return '按平台规则，发布需要三张不同角度实拍图。'

        ai.call_api = fake
        try:
            r = await ai.ai_answer('怎么退款', SimpleNamespace(),
                                   [{'role': 'user', 'content': '怎么发布'}])
        finally:
            ai.call_api = original
        self.assertEqual(captured['history'][0]['content'], '怎么发布')
        self.assertEqual(r['mode'], 'llm')

    def test_knowledge_only_customer_faq(self):
        sources = {c['source'] for c in ai.KNOWLEDGE}
        self.assertEqual(sources, {'ai_service\\knowledge\\faq.md'})
