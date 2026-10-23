"""复现截图中的工单只见汇总问题，验证实际明细、人工确认与原子执行。"""
import json
import time
import sys
from unittest.mock import patch

from cloudflare_test_support import CloudCase


class OfficeTicketTests(CloudCase):
    """仅使用合成账号、内存 SQLite 模拟 D1，不访问生产与付费模型。"""

    def setUp(self):
        """准备两个普通反馈和一个退款工单，内部备注不允许进入助手。"""
        super().setUp()
        # 二十条批次模拟已明确配置的 Paid 查询预算；默认环境另有 Free 边界测试。
        self.api.env.HC_OFFICE_BATCH_LIMIT = '20'
        self.db.execute("UPDATE users SET role='owner' WHERE id=5")
        self.db.executemany('INSERT INTO tickets(id,user_id,type,subject,body,status,created) VALUES(?,?,?,?,?,?,?)', [
            (11, 2, 'other', '发布失败', '上传图片后页面没有反应', 'open', time.time()),
            (12, 3, 'other', '如何修改介绍', '想补充商品使用情况', 'open', time.time()),
            (13, 2, 'refund', '商品不符', '希望核实后退款', 'open', time.time())])
        self.db.execute("INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(11,1,'内部密文不可给模型',1,?)", (time.time(),))
        self.db.commit()

    async def post(self, suffix, body=None, uid=5):
        """调用真实办公路由，身份沿用合成会话。"""
        return await self.req('/api/ai/office' + suffix, uid, 'POST', body or {})

    async def listed(self):
        """获取真实工单快照，缺少入口时直接报断言失败。"""
        result = await self.post('/tickets/list')
        self.assertEqual(result.status, 200, result.body)
        return result.body['tickets']

    async def prepare(self, ids=(11,), action='claim_reply'):
        """用人工核对的正文生成待执行快照，不触发回复或结案。"""
        rows = {row['id']: row for row in await self.listed()}
        result = await self.post('/tickets/prepare', {'items': [
            dict(id=tid, revision=rows[tid]['revision'], action=action,
                 body='已收到反馈，请补充报错页面及出现问题的步骤。', reason='核对反馈后受理并请用户补充信息。')
            for tid in ids]})
        self.assertEqual(result.status, 200, result.body)
        return result.body['proposal_id']

    async def confirm(self, proposal_id, **extra):
        """执行只接受服务端编号与显式确认，不信任客户端替换动作。"""
        return await self.post('/tickets/confirm', dict(proposal_id=proposal_id, confirmed=True, **extra))

    async def draft(self, ids):
        """模拟真实界面携带已经显示给操作者的快照编号。"""
        rows = {row['id']: row for row in await self.listed()}
        return await self.post('/tickets/draft', dict(ticket_ids=ids,
            revisions={str(tid): rows[tid]['revision'] for tid in ids}))

    async def test_chat_lists_real_ticket_details_without_model(self):
        """截图同一句问法必须给明细，即使模型没有 Key 也能工作。"""
        result = await self.post('', dict(question='今天有哪些待处理工单？'))
        self.assertEqual(result.status, 200, result.body)
        self.assertIn('tickets', result.body, '办公助手仍只有汇总，没有工单明细')
        self.assertEqual([t['id'] for t in result.body['tickets']], [11, 12, 13])
        self.assertIn('上传图片', result.body['tickets'][0]['body'])
        self.assertNotIn('内部密文', json.dumps(result.body, ensure_ascii=False))

    async def test_all_process_opens_review_without_mutating(self):
        """全部处理先展示可审阅计划，不能默默批量结案或发送。"""
        result = await self.post('', dict(question='全部处理'))
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(result.body.get('office_tool'), 'tickets')
        self.assertEqual(self.db.execute("SELECT count(*) FROM tickets WHERE status='open'").fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)

    async def test_upstream_readonly_queries_survive_ticket_integration(self):
        """同步新版后仍能查用户、概览及已解决工单，不被待办工具抢走。"""
        self.db.execute("UPDATE tickets SET status='resolved' WHERE id=11")
        for question in ('平台数据概览', '把所有用户列出来', '已解决工单'):
            result = await self.post('', dict(question=question))
            self.assertEqual(result.status, 200, result.body)
            self.assertEqual(result.body.get('mode'), 'rule', question)
        result = await self.post('', dict(question='已解决工单'))
        self.assertIn('发布失败', result.body['answer'])
        self.assertNotIn('如何修改介绍', result.body['answer'])

    async def test_pagination_reports_remaining_instead_of_claiming_all(self):
        """有更多工单时返回总量与下一页，不能把第一页当成全部。"""
        for tid in range(20, 42):
            self.db.execute("INSERT INTO tickets(id,user_id,type,subject,body,status,created) VALUES(?,2,'other','反馈','说明','open',?)", (tid, time.time()))
        result = await self.post('/tickets/list')
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(result.body['total'], 25)
        self.assertEqual(len(result.body['tickets']), 20)
        self.assertTrue(result.body['has_more'])
        next_page = await self.post('/tickets/list', dict(page=2))
        self.assertEqual(len(next_page.body['tickets']), 5)

    async def test_model_failure_still_produces_editable_drafts(self):
        """没有模型服务时仍能逐单给受理草稿，且不冒充已解决。"""
        result = await self.draft([11, 12])
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(len(result.body['items']), 2)
        self.assertTrue(all(item['body'] for item in result.body['items']))
        self.assertEqual(result.body['mode'], 'rule')
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)

    async def test_connected_langgraph_service_receives_only_public_redacted_facts(self):
        """已配置开源服务时真实工具路由须使用它，且不发送内部备注或联系方式。"""
        self.api.env.HC_OFFICE_AGENT_URL = 'https://agent.test.invalid'
        self.api.env.HC_OFFICE_AGENT_TOKEN = 'synthetic-agent-token'
        self.db.execute("UPDATE tickets SET body='联系13812345678，邮箱student@example.invalid' WHERE id=11")
        requests = []

        async def external_service(url, **kwargs):
            """只替代外部网络，业务输入过滤与回复解析仍使用生产代码。"""
            requests.append(dict(url=url, **kwargs))
            async def response_text():
                """返回开源草稿服务的协议，模型没有动作权限。"""
                return json.dumps(dict(engine='langgraph', mode='llm', items=[dict(id=11, body='请补充报错截图。')]))
            from types import SimpleNamespace
            return SimpleNamespace(status=200, text=response_text)

        with patch.object(sys.modules['workers'], 'fetch', external_service, create=True):
            result = await self.draft([11])
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(result.body.get('engine'), 'langgraph')
        self.assertEqual(result.body['items'][0]['body'], '请补充报错截图。')
        self.assertEqual(requests[0]['url'], 'https://agent.test.invalid/office/tickets/draft')
        self.assertNotIn('内部密文', requests[0]['body'])
        self.assertNotIn('13812345678', requests[0]['body'])
        self.assertNotIn('student@example.invalid', requests[0]['body'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)

    async def test_prepare_is_read_only_for_business_and_confirm_is_atomic(self):
        """受理、公开回复、通知、审计和回执在确认后一次提交。"""
        proposal = await self.prepare((11, 12))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)
        result = await self.confirm(proposal)
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(result.body['ticket_ids'], [11, 12])
        self.assertEqual(self.db.execute("SELECT count(*) FROM tickets WHERE status='processing' AND assignee=5").fetchone()[0], 2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM notifications WHERE kind='ticket_reply'").fetchone()[0], 2)
        before = self.db.execute('SELECT count(*) FROM audit').fetchone()[0]
        self.assertEqual((await self.confirm(proposal)).body, result.body)
        self.assertEqual(self.db.execute('SELECT count(*) FROM audit').fetchone()[0], before)

    async def test_default_limit_bounds_every_tool_including_linked_ticket(self):
        """未声明 Paid 预算时按单处理；有关联商品和订单也不能越过 Free 五十查询限制。"""
        del self.api.env.HC_OFFICE_BATCH_LIMIT
        self.db.execute("INSERT INTO products(id,seller_id,title,data) VALUES(101,3,'测试商品','{}')")
        self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,items,status,total) VALUES(101,2,3,'[{\"id\":101}]','paid',100)")
        self.db.execute('UPDATE tickets SET order_id=101,product_id=101 WHERE id=11')
        original = self.api.db._db.prepare
        count = 0

        def limited(sql):
            """按独立语句计入预算，包含 batch 里的全部语句。"""
            nonlocal count
            count += 1
            if count > 50:
                raise RuntimeError('Free D1 query budget exceeded')
            return original(sql)

        with patch.object(self.api.db._db, 'prepare', limited):
            listing = await self.post('/tickets/list')
            self.assertEqual(listing.status, 200, listing.body)
            self.assertEqual(len(listing.body['tickets']), 1)
            self.assertEqual(listing.body['batch_limit'], 1)
            row = listing.body['tickets'][0]
            count = 0
            draft = await self.post('/tickets/draft', dict(ticket_ids=[11], revisions={'11': row['revision']}))
            self.assertEqual(draft.status, 200, draft.body)
            count = 0
            plan = await self.post('/tickets/prepare', dict(items=[dict(id=11, revision=row['revision'],
                action='claim_reply', body='请补充订单证据。', reason='核对后受理。')]))
            self.assertEqual(plan.status, 200, plan.body)
            count = 0
            self.assertEqual((await self.confirm(plan.body['proposal_id'])).status, 200)

    async def test_reply_only_audits_the_human_supplied_reason(self):
        """仅回复也应保存人工处理依据，不能只留任务编号。"""
        proposal = await self.prepare(action='reply')
        result = await self.confirm(proposal)
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(self.db.execute('SELECT status FROM tickets WHERE id=11').fetchone()[0], 'open')
        rows = self.db.execute('SELECT reason FROM audit WHERE ticket_id=11').fetchall()
        self.assertTrue(any('核对反馈后受理' in row['reason'] for row in rows))

    async def test_explicit_confirmation_and_payload_integrity(self):
        """缺少明确确认、替换正文或伪造动作均不得执行。"""
        proposal = await self.prepare()
        result = await self.post('/tickets/confirm', dict(proposal_id=proposal, confirmed=False))
        self.assertEqual(result.status, 400)
        self.assertEqual((await self.confirm(proposal, items=[])).status, 400)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)

    async def test_only_owner_can_use_all_tools(self):
        """开发者及以下角色不能使用办公查询、准备或确认接口。"""
        for uid in (0, 1, 2, 4):
            for path in ('/tickets/list', '/tickets/draft', '/tickets/prepare', '/tickets/confirm'):
                self.assertIn((await self.post(path, uid=uid)).status, (401, 403))
        self.db.execute("UPDATE users SET role='developer' WHERE id=5")
        self.assertEqual((await self.post('/tickets/list')).status, 403)

    async def test_audit_failure_rolls_back_every_ticket_and_reply(self):
        """任何一条审计写入失败，整批工单、回复、通知及任务状态都回滚。"""
        proposal = await self.prepare((11, 12))
        self.db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'failed audit'); END")
        self.assertEqual((await self.confirm(proposal)).status, 500)
        self.assertEqual(self.db.execute("SELECT count(*) FROM tickets WHERE status='open'").fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM notifications').fetchone()[0], 0)
        self.db.execute('DROP TRIGGER reject_audit')
        self.assertEqual((await self.confirm(proposal)).status, 200)

    async def test_new_reply_invalidates_preview(self):
        """等待确认时有新消息，旧建议必须作废，防止覆盖新的处理事实。"""
        proposal = await self.prepare()
        self.db.execute("INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(11,2,'已经解决了',0,?)", (time.time(),))
        self.assertEqual((await self.confirm(proposal)).status, 409)
        self.assertEqual(self.db.execute("SELECT status FROM tickets WHERE id=11").fetchone()[0], 'open')

    async def test_draft_rejects_messages_not_yet_seen_in_the_list(self):
        """生成草稿前新增的消息不能靠静默更新 revision 绕过人工阅读。"""
        rows = {row['id']: row for row in await self.listed()}
        self.db.execute("INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(11,2,'补充新的关键证据',0,?)", (time.time(),))
        result = await self.post('/tickets/draft', dict(ticket_ids=[11], revisions={'11': rows[11]['revision']}))
        self.assertEqual(result.status, 409, result.body)

    async def test_twenty_ticket_batch_keeps_each_d1_statement_below_binding_limit(self):
        """D1 每条查询最多一百个绑定参数；整批仍须在同一原子 batch 中完成。"""
        self.db.execute("UPDATE tickets SET status='resolved' WHERE id=13")
        for tid in range(20, 38):
            self.db.execute("INSERT INTO tickets(id,user_id,type,subject,body,status,created) VALUES(?,2,'other','反馈','说明','open',?)", (tid, time.time()))
        proposal = await self.prepare((11, 12, *range(20, 38)))
        original = self.api.db._db.batch
        batches = []

        async def d1_limited(statements):
            """仅模拟 D1 文档中的参数边界，继续使用真实事务适配执行 SQL。"""
            batches.append(len(statements))
            if any(len(statement.params) > 100 for statement in statements):
                raise RuntimeError('too many SQL variables: D1 maximum 100')
            return await original(statements)

        with patch.object(self.api.db._db, 'batch', d1_limited):
            result = await self.confirm(proposal)
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(len(batches), 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 20)

    async def test_actor_revocation_inside_transaction_blocks_execution(self):
        """读取后被运维撤销 L1，提交时再次校验身份并回滚。"""
        proposal = await self.prepare()
        original = self.api.db.guarded_batch

        async def revoke(*args, **kwargs):
            """模拟授权校验与原子提交之间的角色变化。"""
            self.db.execute("UPDATE users SET role='developer' WHERE id=5")
            return await original(*args, **kwargs)

        with patch.object(self.api.db, 'guarded_batch', revoke):
            self.assertEqual((await self.confirm(proposal)).status, 409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ticket_messages WHERE internal=0').fetchone()[0], 0)

    async def test_self_interest_and_refund_cannot_be_auto_closed(self):
        """自涉工单不可处理，退款和处罚类不能通过批量结案绕过现有流程。"""
        self.db.execute('UPDATE tickets SET user_id=5 WHERE id=12')
        rows = {r['id']: r for r in await self.listed()}
        self.assertFalse(rows[12]['can_process'])
        items = [dict(id=13, revision=rows[13]['revision'], action='resolve_reply',
                      body='已结案', reason='直接结束退款')]
        self.assertEqual((await self.post('/tickets/prepare', dict(items=items))).status, 403)
        self.assertEqual((await self.draft([12])).status, 403)

    async def test_general_ticket_can_be_explicitly_resolved(self):
        """人工核实的一般反馈可以回复并结案，复用现有结案副作用。"""
        result = await self.confirm(await self.prepare(action='resolve_reply'))
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(self.db.execute('SELECT status FROM tickets WHERE id=11').fetchone()[0], 'resolved')
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit WHERE type='ticket_resolved'").fetchone()[0], 1)

    async def test_other_owner_and_expired_proposal_are_rejected(self):
        """预览不能跨账号执行；过期后须重新核对。"""
        proposal = await self.prepare()
        self.db.execute("UPDATE users SET role='owner' WHERE id=1")
        result = await self.post('/tickets/confirm', dict(proposal_id=proposal, confirmed=True), uid=1)
        self.assertEqual(result.status, 403)
        self.db.execute('UPDATE ai_office_jobs SET expires=0 WHERE id=?', (proposal,))
        self.assertEqual((await self.confirm(proposal)).status, 409)
