"""公开 FAQ 边界的失败回归，不连接真实账户或模型供应商。"""

import asyncio
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from huali.bootstrap import create_app
from huali.infrastructure.assistant import LegacyIdentity
from huali.modules.compat.ports import LegacyResponse
from huali.modules.support.assistant.ports import Actor, KnowledgeDocument, ModelAnswer
from huali.modules.support.assistant.service import AssistantService
from huali.shared.errors import ApplicationError
from huali.shared.settings import Settings


class VerifiedIdentity:
    """只接受合成 token，验证重放与账号隔离时仍逐次检查。"""

    async def verify(self, token: str) -> Actor:
        """返回合成账号，不存储 token 或模拟角色提升。"""
        if token not in ("account-a", "account-b"):
            raise ApplicationError("UNAUTHENTICATED", "请先登录", 401)
        return Actor(token[-1])


class PublicKnowledge:
    """测试仅提供一条可核实的公开模拟支付规则。"""

    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        """只有付款主题返回公开规则，未知问题没有依据。"""
        return (
            (
                KnowledgeDocument(
                    "payment", "付款为模拟", "synthetic-v1", "不扣真实款项。"
                ),
            )
            if "付款" in question
            else ()
        )


class RecordingModel:
    """记录本机合成调用，用于断言原始秘密与身份从未进入模型。"""

    def __init__(self, failure: bool = False) -> None:
        """可配置明确故障，不通过真实供应商复现超时。"""
        self.calls: list[tuple[str, str]] = []
        self.failure = failure

    async def answer(self, question: str, context: str) -> ModelAnswer:
        """返回可控答案或安全业务错误，测试不发起任何外部网络。"""
        self.calls.append((question, context))
        await asyncio.sleep(0)
        if self.failure:
            raise ApplicationError("ASSISTANT_UNAVAILABLE", "合成故障", 503)
        return ModelAnswer("付款为模拟，不扣真实款项。", "mock")


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    """验证真实应用用例的来源、隐私、并发与原键恢复行为。"""

    def setUp(self) -> None:
        """每例使用新用例和合成账号，避免共享状态遮住并发问题。"""
        self.model = RecordingModel()
        self.now = 0.0
        self.service = AssistantService(
            VerifiedIdentity(), PublicKnowledge(), self.model, self.next_time
        )

    def next_time(self) -> float:
        """按每次调用三秒推进合成时钟，不使用真实等待验证限额。"""
        self.now += 3
        return self.now

    async def test_concurrent_replay_only_calls_model_once(self) -> None:
        """同账号并发重放同轮次只生成一次，来源仍来自知识端口。"""
        turn = str(uuid4())
        results = await asyncio.gather(
            *[self.service.answer("account-a", turn, "付款是否扣钱") for _ in range(6)]
        )
        self.assertEqual(len(self.model.calls), 1)
        self.assertTrue(all(result.client_turn_id == turn for result in results))
        self.assertEqual(results[0].sources[0].document_id, "payment")

    async def test_different_content_same_turn_conflicts(self) -> None:
        """已有轮次不能换内容；另一个账号不共享缓存结果。"""
        turn = str(uuid4())
        await self.service.answer("account-a", turn, "付款是否扣钱")
        with self.assertRaises(ApplicationError) as error:
            await self.service.answer("account-a", turn, "付款金额")
        self.assertEqual(error.exception.status, 409)
        await self.service.answer("account-b", turn, "付款金额")
        self.assertEqual(len(self.model.calls), 2)

    async def test_raw_input_and_identity_are_never_sent_to_model(self) -> None:
        """自由输入中的未识别私密字符串也只参与本机检索，不进入模型请求。"""
        await self.service.answer("account-a", str(uuid4()), "付款：测试秘密不应外传")
        outbound = str(self.model.calls)
        self.assertNotIn("测试秘密", outbound)
        self.assertNotIn("account-a", outbound)
        self.assertIn("付款为模拟", outbound)

    async def test_sensitive_or_human_or_unknown_never_calls_model(self) -> None:
        """凭据、手机号、人工诉求和无依据问题都只建议人工，不假报接管。"""
        for question in (
            "付款密码是test-secret",
            "付款 Bearer synthetic-secret",
            "付款 联系13800000000",
            "付款，转人工",
            "外星人的问题",
        ):
            result = await self.service.answer("account-a", str(uuid4()), question)
            self.assertTrue(result.handoff.recommended)
            self.assertEqual(result.sources, [])
            self.assertEqual(result.handoff.next_path, "/support/new")
        self.assertEqual(self.model.calls, [])

    async def test_failure_is_terminal_for_same_turn_no_automatic_retry(self) -> None:
        """未知调用结果保留原轮次失败，重复点击不偷偷发起第二次模型调用。"""
        self.model.failure = True
        turn = str(uuid4())
        for _ in range(2):
            with self.assertRaises(ApplicationError):
                await self.service.answer("account-a", turn, "付款是否扣钱")
        self.assertEqual(len(self.model.calls), 1)

    async def test_revoked_identity_cannot_replay_cached_answer(self) -> None:
        """缓存不构成身份旁路，失效账号无法取回旧结果。"""
        with self.assertRaises(ApplicationError) as error:
            await self.service.answer("expired", str(uuid4()), "付款是否扣钱")
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(self.model.calls, [])


class GatewayFixture:
    """记录身份上游调用；不具备任何业务写方法。"""

    def __init__(self, status: int = 200, failure: bool = False) -> None:
        """可控模拟上游身份故障，不把客户端提供的账号视为可信。"""
        self.status = status
        self.failure = failure
        self.calls: list[tuple[str, str, str]] = []

    async def request(
        self, method: str, path: str, token: str, body=None
    ) -> LegacyResponse:
        """仅返回合成身份，参数签名与旧窄网关相同。"""
        self.calls.append((method, path, token))
        if self.failure:
            raise ApplicationError("LEGACY_UNAVAILABLE", "合成断连", 502)
        return LegacyResponse(self.status, {"id": 17})


class IdentityAdapterTests(unittest.IsolatedAsyncioTestCase):
    """核实明确失效与身份服务故障不能混淆。"""

    async def test_identity_queries_only_me_and_returns_trusted_id(self) -> None:
        """真实网关适配只调用原 me，不查询订单或将角色交给模型。"""
        gateway = GatewayFixture()
        actor = await LegacyIdentity(gateway).verify("synthetic-session")
        self.assertEqual(actor.user_id, "17")
        self.assertEqual(gateway.calls, [("GET", "/api/me", "synthetic-session")])

    async def test_unavailable_identity_is_503_not_401(self) -> None:
        """上游超时保留登录状态；只有旧服务明确 401 才清会话。"""
        for gateway, expected in (
            (GatewayFixture(failure=True), 503),
            (GatewayFixture(502), 503),
            (GatewayFixture(401), 401),
            (GatewayFixture(403), 403),
        ):
            with self.assertRaises(ApplicationError) as error:
                await LegacyIdentity(gateway).verify("synthetic-session")
            self.assertEqual(error.exception.status, expected)


class AssistantBoundaryTests(unittest.TestCase):
    """先锁定未登录和严格输入边界，避免新增接口直接暴露模型。"""

    def test_unauthenticated_question_is_rejected(self) -> None:
        """缺少原会话时返回 401，不能假装已经核实用户身份。"""
        with TestClient(create_app(Settings(environment="test"))) as client:
            result = client.post(
                "/api/v1/support/assistant/answer",
                json={
                    "client_turn_id": "3f794a1a-969a-4648-85b1-3009cc70db2c",
                    "question": "付款是真的扣钱吗",
                },
            )
        self.assertEqual(result.status_code, 401)

    def test_hidden_context_is_not_accepted(self) -> None:
        """客户端不能自报角色、订单内容或系统提示词。"""
        with TestClient(create_app(Settings(environment="test"))) as client:
            result = client.post(
                "/api/v1/support/assistant/answer",
                json={
                    "client_turn_id": "3f794a1a-969a-4648-85b1-3009cc70db2c",
                    "question": "怎么付款",
                    "user_id": 1,
                },
            )
        self.assertEqual(result.status_code, 422)
