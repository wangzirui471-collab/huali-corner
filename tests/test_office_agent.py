"""用真实 LangGraph 运行草稿流程；模型以确定性函数替代，不调用收费 API。"""
import importlib
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('langgraph'), '可选办公服务未安装 LangGraph；按 ai_service/requirements-office.txt 安装后单独验证')
class OfficeAgentTests(unittest.TestCase):
    """验证开源编排实际运行、输出只含草稿及异常降级。"""

    def invoke(self, tickets, generate):
        """通过公开入口运行真实图，缺失实现时报告明确失败。"""
        spec = importlib.util.find_spec('ai_service.office_agent')
        self.assertIsNotNone(spec, '缺少开源 LangGraph 办公编排接入')
        return importlib.import_module('ai_service.office_agent').draft_tickets(tickets, generate)

    def tickets(self):
        """返回一条已经授权的公开工单资料。"""
        return [dict(id=11, subject='图片上传失败', body='请问怎么办', messages=[])]

    def test_real_graph_generates_preview_without_execution_tool(self):
        """真实图只能返回公开回复草稿，不能输出可执行 SQL 或处罚动作。"""
        result = self.invoke(self.tickets(), lambda tickets: [dict(id=11, body='请补充报错信息。', action='refund', sql='DELETE')])
        self.assertEqual(result['engine'], 'langgraph')
        self.assertEqual(result['mode'], 'llm')
        self.assertEqual(result['items'], [dict(id=11, body='请补充报错信息。')])

    def test_provider_failure_falls_back_without_false_success(self):
        """模型超时或不可用仍返回明确的基础草稿，不声称已经办完。"""
        def unavailable(tickets):
            """模拟外部模型不可用。"""
            raise TimeoutError('upstream timeout')
        result = self.invoke(self.tickets(), unavailable)
        self.assertEqual(result['mode'], 'rule')
        self.assertIn('补充', result['items'][0]['body'])

    def test_model_cannot_swap_ticket_ids(self):
        """模型替换工单编号时整组降级，不能把回复发送到其他工单。"""
        result = self.invoke(self.tickets(), lambda tickets: [dict(id=999, body='错误对象')])
        self.assertEqual(result['mode'], 'rule')
        self.assertEqual(result['items'][0]['id'], 11)

    def test_private_notes_are_removed_before_generation(self):
        """额外混入内部备注时，图入口也必须剔除而不是只依赖上游。"""
        tickets = self.tickets()
        tickets[0]['messages'] = [dict(body='不能进模型的内部备注', internal=1), dict(body='公开反馈', internal=0)]
        seen = []

        def generate(public):
            """记录送给外部模型的真实入参。"""
            seen.extend(public)
            return [dict(id=11, body='请补充截图。')]
        self.invoke(tickets, generate)
        self.assertNotIn('内部备注', str(seen))
        self.assertIn('公开反馈', str(seen))

    def test_invalid_or_unbounded_input_is_rejected(self):
        """无界工单或重复编号不能进入模型调用阶段。"""
        with self.assertRaises(ValueError):
            self.invoke(self.tickets() * 21, lambda tickets: [])
