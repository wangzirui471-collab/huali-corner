"""公开问答应用服务：身份先核实，审核资料后调用模型，业务数据零写入。"""

import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass

from huali.modules.support.assistant.ports import (
    IdentityPort,
    KnowledgeDocument,
    KnowledgePort,
    ModelPort,
)
from huali.modules.support.assistant.rules import requires_handoff
from huali.modules.support.assistant.schema import AnswerData, Handoff, Source
from huali.shared.errors import ApplicationError


@dataclass
class Turn:
    """进程内有限去重记录，不保存 token，不能承诺重启后仍不重复计费。"""

    digest: str
    started_at: float
    task: asyncio.Task[AnswerData]


@dataclass
class Usage:
    """单进程滚动日配额，不记录问题或账号私密资料。"""

    started_at: float
    latest_at: float
    count: int


def observe_result(task: asyncio.Task[AnswerData]) -> None:
    """即使页面取消等待，也回收后台终态异常；不记录问题或回答。"""
    if not task.cancelled():
        task.exception()


class AssistantService:
    """唯一问答用例；不持有订单、工单、账本或用户资料写端口。"""

    def __init__(
        self,
        identity: IdentityPort,
        knowledge: KnowledgePort,
        model: ModelPort | None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """注入三类依赖及秒级单调时钟，去重仅限本进程十分钟。"""
        self.identity = identity
        self.knowledge = knowledge
        self.model = model
        self.clock = clock
        self.turns: dict[tuple[str, str], Turn] = {}
        self.usage: dict[str, Usage] = {}

    def consume_quota(self, user_id: str, now: float) -> None:
        """继承原问答每账号30轮和两秒间隔，重放不重复占用；重启会重置。"""
        self.usage = {
            actor: usage
            for actor, usage in self.usage.items()
            if now - usage.started_at < 86400
        }
        usage = self.usage.get(user_id)
        if usage is None:
            if len(self.usage) >= 1000:
                raise ApplicationError("ASSISTANT_BUSY", "问答繁忙，请稍后再试", 503)
            self.usage[user_id] = Usage(now, now, 1)
            return
        if usage.count >= 30 or now - usage.latest_at < 2:
            raise ApplicationError(
                "RATE_LIMITED",
                "提问过于频繁或本日额度已用完，可改由人工核实",
                429,
                retry_after=str(max(1, int(86400 - (now - usage.started_at))))
                if usage.count >= 30
                else "2",
            )
        usage.count += 1
        usage.latest_at = now

    async def answer(self, token: str, turn_id: str, question: str) -> AnswerData:
        """每次重放也核实会话，同账号同轮次异内容拒绝，不自动重做未知调用。"""
        actor = await self.identity.verify(token)
        key = (actor.user_id, turn_id)
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()
        now = self.clock()
        self.turns = {
            entry: turn
            for entry, turn in self.turns.items()
            if not turn.task.done() or now - turn.started_at < 600
        }
        turn = self.turns.get(key)
        if turn is not None:
            if turn.digest != digest:
                raise ApplicationError(
                    "IDEMPOTENCY_MISMATCH", "本轮问题已变化，请使用新的提问编号", 409
                )
        else:
            if len(self.turns) >= 256:
                raise ApplicationError("ASSISTANT_BUSY", "问答繁忙，请稍后再试", 503)
            reason, documents = self.prepare(question)
            self.consume_quota(actor.user_id, now)
            # 此段至创建任务没有 await，同一事件循环的并发不会重复建单轮任务。
            task = asyncio.create_task(self._respond(turn_id, reason, documents))
            task.add_done_callback(observe_result)
            turn = Turn(digest, now, task)
            self.turns[key] = turn
        # 取消浏览器等待不自动重复调用供应商；已有调用终态仍留作同轮核对。
        return await asyncio.shield(turn.task)

    def prepare(self, question: str) -> tuple[str, tuple[KnowledgeDocument, ...]]:
        """调用前的知识或配置失败不占轮次，恢复后可安全沿用原编号重试。"""
        reason = requires_handoff(question)
        documents = () if reason else self.knowledge.search(question)
        if documents and self.model is None:
            raise ApplicationError(
                "ASSISTANT_NOT_CONFIGURED", "尚未连接公开问答服务，输入已保留", 503
            )
        return reason, documents

    async def _respond(
        self, turn_id: str, reason: str, documents: tuple[KnowledgeDocument, ...]
    ) -> AnswerData:
        """只把已审核公开资料与主题交给模型，不保留或外发自由输入。"""
        if reason or not documents:
            reason = reason or "现有公开规则无法确认这个问题，请先提交工单由人工核实。"
            return AnswerData(
                client_turn_id=turn_id,
                answer_text=reason,
                mode="handoff",
                sources=[],
                handoff=Handoff(recommended=True, reason=reason),
            )
        if self.model is None:
            raise ApplicationError(
                "ASSISTANT_NOT_CONFIGURED", "尚未连接公开问答服务，输入已保留", 503
            )
        context = "\n\n".join(
            f"【{document.title}】\n{document.content}" for document in documents
        )
        try:
            # 首片只解释公开规则主题，原始自由输入即使含未识别秘密也不外发。
            public_question = "请根据资料说明：" + "、".join(
                document.title for document in documents
            )
            result = await asyncio.wait_for(
                self.model.answer(public_question, context), 20
            )
        except TimeoutError as error:
            raise ApplicationError(
                "ASSISTANT_UNAVAILABLE", "回答超时，输入已保留，可改由人工核实", 503
            ) from error
        return AnswerData(
            client_turn_id=turn_id,
            answer_text=result.answer_text,
            mode=result.mode,
            sources=[
                Source(
                    document_id=document.document_id,
                    title=document.title,
                    version=document.version,
                    content=document.content,
                )
                for document in documents
            ],
            handoff=Handoff(recommended=False),
        )
