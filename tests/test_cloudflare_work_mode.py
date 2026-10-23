"""工作模式 D1 版：工具目录、读工具、proposal→confirm、owner 权限、多步与演示商品闭环。

只用内存 SQLite 模拟 D1 与合成账号，不访问生产库、不调用付费模型；
规划器用确定性桩替换，验证「查询→批量下架」「生成预览→确认入库」的衔接。
"""
import json
import time
import unittest
from unittest.mock import patch

from cloudflare_test_support import CloudCase


def _scripted(steps):
    """按已执行步数返回脚本下一步；与 eval_work_agent.py 同一思路。"""
    async def fake(question, tools, observations, env):
        return steps[min(len(observations or []), len(steps) - 1)]
    return fake


class WorkModeTests(CloudCase):
    def setUp(self):
        super().setUp()
        self.db.execute("UPDATE users SET role='owner' WHERE id=5")
        self.db.execute("INSERT INTO tickets(id,user_id,type,subject,body,status,created) "
                        "VALUES(11,2,'other','工作模式工单','用于 D1 测试','open',?)", (time.time(),))
        self.db.execute("INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,"
                        "region,status,data,created) VALUES(21,2,'宿舍好物·收纳盒','living',1500,0,"
                        "'pickup','校内面交','available','{}',?)", (time.time(),))
        self.db.commit()

    # ---- 调用辅助 ----------------------------------------------------------
    async def tools(self, uid=5):
        return await self.req('/api/ai/work/tools', uid)

    async def chat(self, q, uid=5):
        return await self.req('/api/ai/work/chat', uid, 'POST', {'question': q})

    async def call(self, tool, args=None, token=None, uid=5):
        return await self.req('/api/ai/work/call', uid, 'POST',
                              {'tool': tool, 'args': args or {}, 'token': token})

    async def confirm(self, token, uid=5):
        return await self.req('/api/ai/work/confirm', uid, 'POST', {'token': token})

    def scalar(self, sql, params=()):
        return self.db.execute(sql, params).fetchone()[0]

    # ---- 目录与权限 --------------------------------------------------------
    async def test_tools_catalog_covers_local_registry(self):
        result = await self.tools()
        self.assertEqual(result.status, 200, result.body)
        names = {t['name'] for t in result.body['tools']}
        for name in ('overview', 'users', 'products', 'orders', 'tickets', 'audit', 'stats',
                     'rooms', 'messages', 'moderation', 'credit', 'offers', 'posts', 'ledger',
                     'sellers', 'demo_generate', 'user_role', 'user_ban', 'user_credit',
                     'product_promote', 'product_batch_delist', 'product_bulk_moderate',
                     'content_remove', 'demo_cleanup', 'backup', 'user_disable', 'user_revoke',
                     'product_moderate', 'ticket_reply', 'ticket_resolve', 'notification_send',
                     'ai_settings', 'demo_publish'):
            self.assertIn(name, names)
        self.assertEqual(len(names), 37)

    async def test_non_owner_forbidden(self):
        for uid in (1, 2, 4):
            result = await self.tools(uid)
            self.assertEqual(result.status, 403, (uid, result.body))
        result = await self.chat('平台概览', uid=2)
        self.assertEqual(result.status, 403, result.body)

    # ---- 读工具 ------------------------------------------------------------
    async def test_read_tools_return_deterministic_answers(self):
        cases = [
            ('overview', {}, '活跃用户'),
            ('users', {'q': '测试'}, '找到'),
            ('tickets', {'status': 'open'}, '工作模式工单'),
            ('audit', {}, '审计记录'),
            ('stats', {'days': 7}, '最近 7 天新增'),
            ('rooms', {}, '会话'),
            ('moderation', {}, '举报'),
            ('credit', {}, '信誉'),
            ('offers', {}, '出价'),
            ('posts', {}, '帖子'),
            ('ledger', {}, '账本'),
            ('sellers', {}, '卖家'),
        ]
        for tool, args, needle in cases:
            result = await self.call(tool, args)
            self.assertEqual(result.status, 200, (tool, result.body))
            body = result.body
            self.assertIn('answer', body, tool)
            self.assertIn('items', body, tool)
            self.assertIn(needle, body['answer'] + json.dumps(body['items'], ensure_ascii=False), tool)

    async def test_user_detail_masks_phone_and_logs_reveal(self):
        result = await self.call('user_detail', {'id': 2})
        self.assertEqual(result.status, 200, result.body)
        self.assertNotIn('u2@test.invalid', json.dumps(result.body, ensure_ascii=False))
        revealed = await self.call('user_detail', {'id': 2, 'reveal': True})
        self.assertEqual(revealed.status, 200, revealed.body)
        self.assertIn('u2@test.invalid', json.dumps(revealed.body, ensure_ascii=False))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='pii_view' AND target=2"), 1)

    async def test_messages_read_writes_chat_view_audit(self):
        self.db.execute("INSERT INTO messages(id,room_id,user_id,body,created) VALUES(31,1,2,'在吗',?)",
                        (time.time(),))
        self.db.commit()
        result = await self.call('messages', {'room': 1})
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='chat_view' AND target=1"), 1)
        bad = await self.call('messages', {'room': 999})
        self.assertEqual(bad.status, 404, bad.body)

    # ---- 写工具：只出 proposal，不落库 --------------------------------------
    async def test_write_tools_only_propose_without_mutation(self):
        cases = [
            ('user_role', {'target': 2, 'role': 'support'}),
            ('user_disable', {'target': 2}),
            ('user_revoke', {'target': 2}),
            ('user_ban', {'target': 2, 'banned': True, 'reason': '测试'}),
            ('product_moderate', {'id': 21, 'action': 'delist', 'reason': '测试'}),
            ('product_promote', {'id': 21, 'tier': '1d', 'reason': '测试'}),
            ('product_batch_delist', {'seller': 2, 'reason': '测试'}),
            ('product_bulk_moderate', {'q': '宿舍', 'action': 'delist', 'reason': '测试'}),
            ('ticket_reply', {'id': 11, 'body': '请补充信息'}),
            ('ticket_resolve', {'id': 11, 'outcome': 'claim', 'reason': '核实中'}),
            ('notification_send', {'target': 2, 'body': '测试通知'}),
            ('content_remove', {'kind': 'post', 'id': 9999, 'reason': '测试'}),
        ]
        for tool, args in cases:
            if tool == 'content_remove':
                continue  # 帖子不存在，单独覆盖 404 分支
            result = await self.call(tool, args)
            self.assertEqual(result.status, 200, (tool, result.body))
            body = result.body
            self.assertTrue(body.get('token'), tool)
            self.assertTrue(body.get('proposal'), tool)
            self.assertEqual(body['proposal']['tool'], tool)
        # proposal 阶段不写库
        self.assertEqual(self.scalar("SELECT role FROM users WHERE id=2"), 'user')
        self.assertEqual(self.scalar("SELECT status FROM users WHERE id=2"), 'active')
        self.assertEqual(self.scalar("SELECT status FROM products WHERE id=21"), 'available')
        self.assertEqual(self.scalar("SELECT status FROM tickets WHERE id=11"), 'open')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM notifications'), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type LIKE 'ai_work%'"), 0)

    async def test_proposal_rejects_missing_target_before_card(self):
        result = await self.call('user_role', {'target': 999, 'role': 'support'})
        self.assertEqual(result.status, 404, result.body)
        result = await self.call('user_ban', {'target': 5, 'banned': True, 'reason': 'x'})
        self.assertEqual(result.status, 403, result.body)  # 所有者账号不能被调整
        result = await self.call('user_role', {'target': 5, 'role': 'user'})
        self.assertEqual(result.status, 403, result.body)  # 不能对自己执行

    async def test_credit_requires_resolved_ticket(self):
        result = await self.call('user_credit', {'target': 2, 'delta': 5, 'reason': 'x', 'ticket': 11})
        self.assertEqual(result.status, 400, result.body)  # 工单未结案

    # ---- 确认执行 ----------------------------------------------------------
    async def test_confirm_executes_and_writes_audit(self):
        result = await self.call('user_role', {'target': 2, 'role': 'support'})
        token = result.body['token']
        self.assertEqual(self.scalar("SELECT role FROM users WHERE id=2"), 'user')
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        self.assertTrue(done.body['ok'])
        self.assertEqual(self.scalar("SELECT role FROM users WHERE id=2"), 'support')
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM sessions WHERE user_id=2"), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='ai_work_role' AND target=2"), 1)
        self.assertEqual(self.scalar("SELECT state FROM ai_office_jobs WHERE id=?", (token,)), 'completed')

    async def test_confirm_is_idempotent(self):
        result = await self.call('user_revoke', {'target': 2})
        token = result.body['token']
        first = await self.confirm(token)
        self.assertEqual(first.status, 200, first.body)
        again = await self.confirm(token)
        self.assertEqual(again.status, 200, again.body)
        self.assertTrue(again.body['ok'])
        # 回执形状与首次一致，只是多一个 repeat 标记（前端可原样渲染）。
        self.assertTrue(again.body.get('repeat'))
        self.assertEqual(again.body['tool'], 'user_revoke')
        self.assertEqual(again.body['result'], first.body['result'])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='ai_work_user_revoke'"), 1)

    async def test_invalid_foreign_and_expired_tokens(self):
        bad = await self.confirm('0' * 32)
        self.assertEqual(bad.status, 404, bad.body)
        result = await self.call('user_revoke', {'target': 2})
        token = result.body['token']
        # 另一个 owner（用户 4 提升）不能执行别人的计划
        self.db.execute("UPDATE users SET role='owner' WHERE id=4")
        self.db.commit()
        foreign = await self.confirm(token, uid=4)
        self.assertEqual(foreign.status, 403, foreign.body)
        # 过期计划
        self.db.execute('UPDATE ai_office_jobs SET expires=? WHERE id=?', (time.time() - 1, token))
        self.db.commit()
        expired = await self.confirm(token)
        self.assertEqual(expired.status, 409, expired.body)

    async def test_ban_flow_without_orders(self):
        result = await self.call('user_ban', {'target': 3, 'banned': True, 'reason': '违规'})
        token = result.body['token']
        self.assertEqual(self.scalar("SELECT status FROM users WHERE id=3"), 'active')
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(self.scalar("SELECT status FROM users WHERE id=3"), 'banned')
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM sessions WHERE user_id=3"), 0)

    async def test_content_remove_flow(self):
        self.db.execute("INSERT INTO posts(id,user_id,topic,body,created) VALUES(41,2,'吐槽','内容',?)",
                        (time.time(),))
        self.db.commit()
        result = await self.call('content_remove', {'kind': 'post', 'id': 41, 'reason': '测试'})
        token = result.body['token']
        self.assertEqual(self.scalar('SELECT removed FROM posts WHERE id=41'), 0)
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(self.scalar('SELECT removed FROM posts WHERE id=41'), 1)
        missing = await self.call('content_remove', {'kind': 'post', 'id': 9999, 'reason': 'x'})
        self.assertEqual(missing.status, 404, missing.body)

    async def test_backup_writes_archive_and_audit(self):
        result = await self.call('backup', {})
        token = result.body['token']
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='ai_work_backup'"), 1)
        keys = list(self.bucket.objects)
        self.assertTrue(any(k.startswith('backups/') for k in keys), keys)

    async def test_ai_settings_flow(self):
        result = await self.call('ai_settings', {'enabled': False, 'daily_limit': 20})
        token = result.body['token']
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        row = self.db.execute('SELECT enabled,daily_limit FROM ai_settings WHERE id=1').fetchone()
        self.assertEqual((row[0], row[1]), (0, 20))

    # ---- 账号动作与多步 ----------------------------------------------------
    async def test_account_action_routes_to_proposal_without_model(self):
        result = await self.chat('把 测试用户2 降为客服')
        self.assertEqual(result.status, 200, result.body)
        body = result.body
        self.assertTrue(body.get('proposal'), body)
        self.assertEqual(body['proposal']['tool'], 'user_role')
        self.assertEqual(body['proposal']['args']['role'], 'support')
        self.assertTrue(body.get('token'))

    async def test_owner_target_refused_in_chat(self):
        result = await self.chat('把 测试用户5 设为管理员')
        self.assertEqual(result.status, 200, result.body)
        self.assertIsNone(result.body.get('proposal'))
        self.assertIn('所有者', result.body['answer'])

    async def test_rule_fallback_overview_without_model(self):
        result = await self.chat('平台概览')
        self.assertEqual(result.status, 200, result.body)
        self.assertIn('活跃用户', result.body['answer'])
        self.assertFalse(result.body.get('proposal'))

    async def test_multi_step_query_then_bulk_delist(self):
        """ReAct：先查商品，再批量下架；确认前不落库。"""
        steps = [{'tool': 'products', 'args': {'q': '宿舍'}},
                 {'tool': 'product_bulk_moderate', 'args': {'q': '宿舍', 'action': 'delist', 'reason': '评测'}}]
        with patch('app.cloudflare.work_mode.work_plan', _scripted(steps)):
            result = await self.chat('把宿舍好物全部下架')
        self.assertEqual(result.status, 200, result.body)
        body = result.body
        self.assertTrue(body.get('proposal'), body)
        self.assertEqual(body['proposal']['tool'], 'product_bulk_moderate')
        self.assertIn('命中 1 件', body['proposal']['summary'])
        self.assertEqual(self.scalar("SELECT status FROM products WHERE id=21"), 'available')
        done = await self.confirm(body['token'])
        self.assertEqual(done.status, 200, done.body)
        row = self.db.execute('SELECT status,delisted_by FROM products WHERE id=21').fetchone()
        self.assertEqual((row[0], row[1]), ('removed', 5))

    async def test_multi_step_stops_at_final(self):
        steps = [{'tool': 'overview', 'args': {}}, {'tool': 'final', 'args': {}}]
        with patch('app.cloudflare.work_mode.work_plan', _scripted(steps)):
            result = await self.chat('平台怎么样')
        self.assertEqual(result.status, 200, result.body)
        self.assertIn('活跃用户', result.body['answer'])
        self.assertFalse(result.body.get('proposal'))

    async def test_demo_generate_then_publish_flow(self):
        """「生成预览 → 确认 → 批量入库」：预览不经模型转抄，确认后才写库。"""
        steps = [{'tool': 'demo_generate', 'args': {'prompt': '宿舍好物', 'count': 3}},
                 {'tool': 'demo_publish', 'args': {}}]
        with patch('app.cloudflare.work_mode.work_plan', _scripted(steps)):
            result = await self.chat('发布 3 件宿舍好物演示商品')
        self.assertEqual(result.status, 200, result.body)
        body = result.body
        self.assertTrue(body.get('proposal'), body)
        self.assertEqual(body['proposal']['tool'], 'demo_publish')
        self.assertEqual(len(body['proposal']['args']['items']), 3)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM products WHERE status='available'"), 1)
        done = await self.confirm(body['token'])
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(done.body['result']['count'], 3)
        virtual = self.scalar("SELECT COUNT(*) FROM products WHERE data LIKE '%virtual%'")
        self.assertEqual(virtual, 3)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='ai_work_demo_publish'"), 1)

    async def test_rule_fallback_publishes_demo(self):
        """规划器挂了也要能出「预览 + 确认卡」，且 proposal 阶段不落库。"""
        async def boom(question, tools, observations, env):
            raise RuntimeError('model down')
        with patch('app.cloudflare.work_mode.work_plan', boom):
            result = await self.chat('发布 3 件宿舍好物演示商品')
        self.assertEqual(result.status, 200, result.body)
        body = result.body
        self.assertTrue(body.get('proposal'), body)
        self.assertEqual(body['proposal']['tool'], 'demo_publish')
        self.assertEqual(len(body['proposal']['args']['items']), 3)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM products WHERE data LIKE '%virtual%'"), 0)
        done = await self.confirm(body['token'])
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(done.body['result']['count'], 3)

    async def test_demo_generate_direct_call_returns_preview_only(self):
        result = await self.call('demo_generate', {'prompt': '二手书', 'count': 2})
        self.assertEqual(result.status, 200, result.body)
        items = result.body['data']['items']
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i['category'] == 'books' for i in items))
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'), 1)  # 只有 setUp 那件

    async def test_demo_cleanup_flow(self):
        self.db.execute("INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,"
                        "region,status,data,created) VALUES(22,5,'演示·台灯','living',900,0,'pickup',"
                        "'校内面交','available','{\"virtual\": true}',?)", (time.time(),))
        self.db.commit()
        result = await self.call('demo_cleanup', {})
        token = result.body['token']
        done = await self.confirm(token)
        self.assertEqual(done.status, 200, done.body)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM products'), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE type='ai_work_demo_cleanup'"), 1)


if __name__ == '__main__':
    unittest.main()
