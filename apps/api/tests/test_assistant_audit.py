"""独立复核公开问答的恢复、取消、重放、过期和账号配额，不访问外部服务。"""

import asyncio
import unittest
from http.client import BadStatusLine
from unittest.mock import patch
from uuid import uuid4

from huali.infrastructure.assistant import LegacyIdentity, LocalFaqModel
from huali.infrastructure.legacy import LocalLegacyGateway
from huali.modules.support.assistant.ports import Actor, KnowledgeDocument, ModelAnswer
from huali.modules.support.assistant.service import AssistantService
from huali.shared.errors import ApplicationError


class AuditIdentity:
    """提供可撤销的合成身份，验证缓存不能绕过每次身份检查。"""

    def __init__(self) -> None:
        """默认身份有效；故障状态由各测试显式设置。"""
        self.status = 200

    async def verify(self, token: str) -> Actor:
        """仅把合成令牌尾部作为账号，不执行网络或读取真实会话。"""
        if self.status != 200:
            raise ApplicationError("IDENTITY_AUDIT", "合成身份故障", self.status)
        return Actor(token)


class AuditKnowledge:
    """可模拟资料暂时不可读，恢复后提供唯一合成公开来源。"""

    def __init__(self) -> None:
        """资料默认可读，失败不会被伪装成无匹配。"""
        self.available = True

    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        """返回合成资料或明确的调用前故障。"""
        if not self.available:
            raise ApplicationError("KNOWLEDGE_UNAVAILABLE", "合成知识故障", 503)
        return (KnowledgeDocument("audit", "合成公开规则", "audit-v1", "合成资料。"),)


class AuditModel:
    """模型可暂停至显式释放，用于准确验证取消与并发期间的调用次数。"""

    def __init__(self) -> None:
        """默认直接回答；需要并发窗口时才启用等待。"""
        self.calls = 0
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None

    async def answer(self, question: str, context: str) -> ModelAnswer:
        """记录调用边界，不执行任何供应商请求。"""
        self.calls += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        return ModelAnswer("合成规则答案。", "mock")


class AssistantAuditTests(unittest.IsolatedAsyncioTestCase):
    """用可控时钟和合成端口复核对用户可见的恢复与隔离行为。"""

    def setUp(self) -> None:
        """每例独立用例与时钟，禁止前例缓存掩盖调用次数。"""
        self.now = 1000.0
        self.identity = AuditIdentity()
        self.knowledge = AuditKnowledge()
        self.model = AuditModel()
        self.service = AssistantService(
            self.identity, self.knowledge, self.model, clock=lambda: self.now
        )

    async def test_knowledge_recovers_with_original_turn(self) -> None:
        """调用前知识故障恢复后可沿用原轮次，失败不扣账号额度。"""
        turn = str(uuid4())
        self.knowledge.available = False
        with self.assertRaises(ApplicationError) as failure:
            await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(failure.exception.status, 503)
        self.assertEqual(self.model.calls, 0)
        self.knowledge.available = True
        result = await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(result.mode, "mock")
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.service.usage["actor-a"].count, 1)

    async def test_model_configuration_recovers_with_original_turn(self) -> None:
        """未装配模型时未发起调用，补齐装配后原轮次安全可重试。"""
        turn = str(uuid4())
        self.service.model = None
        with self.assertRaises(ApplicationError) as failure:
            await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(failure.exception.code, "ASSISTANT_NOT_CONFIGURED")
        self.service.model = self.model
        result = await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(result.client_turn_id, turn)
        self.assertEqual(self.model.calls, 1)

    async def test_cancelled_waiter_replays_keep_one_model_call(self) -> None:
        """页面取消等待后，并发原键重试仍等待同一次模型调用终态。"""
        turn = str(uuid4())
        self.model.release = asyncio.Event()
        first = asyncio.create_task(
            self.service.answer("actor-a", turn, "公开付款规则")
        )
        await asyncio.wait_for(self.model.started.wait(), 2)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        replays = [
            asyncio.create_task(self.service.answer("actor-a", turn, "公开付款规则"))
            for _ in range(4)
        ]
        await asyncio.sleep(0)
        self.assertEqual(self.model.calls, 1)
        self.model.release.set()
        results = await asyncio.gather(*replays)
        self.assertTrue(all(result.client_turn_id == turn for result in results))
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.service.usage["actor-a"].count, 1)

    async def test_cache_replay_still_checks_identity(self) -> None:
        """已有答案缓存后撤销身份或身份服务故障，都不能通过原键绕过。"""
        turn = str(uuid4())
        await self.service.answer("actor-a", turn, "公开付款规则")
        for status in (401, 503):
            self.identity.status = status
            with self.assertRaises(ApplicationError) as failure:
                await self.service.answer("actor-a", turn, "公开付款规则")
            self.assertEqual(failure.exception.status, status)
        self.assertEqual(self.model.calls, 1)

    async def test_two_second_limit_does_not_block_replay_or_other_actor(self) -> None:
        """两秒内新轮次受限，原键和另一个账号仍可使用。"""
        turn = str(uuid4())
        await self.service.answer("actor-a", turn, "公开付款规则")
        with self.assertRaises(ApplicationError) as failure:
            await self.service.answer("actor-a", str(uuid4()), "公开付款规则")
        self.assertEqual(failure.exception.status, 429)
        await self.service.answer("actor-a", turn, "公开付款规则")
        await self.service.answer("actor-b", str(uuid4()), "公开付款规则")
        self.assertEqual(self.model.calls, 2)
        self.now += 2
        await self.service.answer("actor-a", str(uuid4()), "公开付款规则")
        self.assertEqual(self.model.calls, 3)

    async def test_daily_limit_and_expiration_allow_next_window(self) -> None:
        """单账号三十轮后拒绝新轮次，另一账号及次日窗口不受影响。"""
        turn = ""
        for _ in range(30):
            turn = str(uuid4())
            await self.service.answer("actor-a", turn, "公开付款规则")
            self.now += 2
        with self.assertRaises(ApplicationError) as failure:
            await self.service.answer("actor-a", str(uuid4()), "公开付款规则")
        self.assertEqual(failure.exception.status, 429)
        await self.service.answer("actor-a", turn, "公开付款规则")
        await self.service.answer("actor-b", str(uuid4()), "公开付款规则")
        self.assertEqual(self.model.calls, 31)
        self.now = 1000.0 + 86400
        await self.service.answer("actor-a", str(uuid4()), "公开付款规则")
        self.assertEqual(self.model.calls, 32)

    async def test_expired_turn_can_generate_again_as_documented(self) -> None:
        """十分钟后重放不承诺持久去重，实际会发起新调用。"""
        turn = str(uuid4())
        await self.service.answer("actor-a", turn, "公开付款规则")
        self.now += 599
        await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(self.model.calls, 1)
        self.now += 1
        await self.service.answer("actor-a", turn, "公开付款规则")
        self.assertEqual(self.model.calls, 2)


class AssistantHttpFaultAuditTests(unittest.IsolatedAsyncioTestCase):
    """模拟 HTTP 协议损坏，确保基础设施故障继续使用可恢复的服务错误。"""

    async def test_bad_identity_http_is_503(self) -> None:
        """身份端口收到坏状态行时不能漏成未知500或错误401。"""
        identity = LegacyIdentity(LocalLegacyGateway("http://127.0.0.1:18081"))
        with patch("huali.infrastructure.legacy.build_opener") as opener:
            opener.return_value.open.side_effect = BadStatusLine("synthetic-invalid")
            with self.assertRaises(ApplicationError) as failure:
                await identity.verify("synthetic-session")
        self.assertEqual(failure.exception.status, 503)

    async def test_bad_model_http_is_503(self) -> None:
        """模型端口收到坏状态行时返回503，原轮次可保留明确故障。"""
        model = LocalFaqModel("http://127.0.0.1:18089", "synthetic-service-token")
        with patch("huali.infrastructure.assistant.build_opener") as opener:
            opener.return_value.open.side_effect = BadStatusLine("synthetic-invalid")
            with self.assertRaises(ApplicationError) as failure:
                await model.answer("公开规则", "公开资料")
        self.assertEqual(failure.exception.status, 503)
