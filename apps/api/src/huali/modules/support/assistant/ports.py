"""公开问答依赖的窄端口，模型永远接触不到会话和旧业务 writer。"""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Actor:
    """原服务已核实的账号编号；不携带令牌、电话、角色或其他资料。"""

    user_id: str


@dataclass(frozen=True)
class KnowledgeDocument:
    """服务端审核过的公开规则；版本来自内容摘要，不能由模型编造。"""

    document_id: str
    title: str
    version: str
    content: str


@dataclass(frozen=True)
class ModelAnswer:
    """模型只返回纯文本和运行模式，不拥有来源或业务动作决定权。"""

    answer_text: str
    mode: Literal["mock", "llm"]


class IdentityPort(Protocol):
    """核实原会话，身份故障与明确失效分别处理。"""

    async def verify(self, token: str) -> Actor:
        """仅返回可信账号编号，禁止将不透明 token 当作模型上下文。"""
        ...


class KnowledgePort(Protocol):
    """只查询明确审核清单，不接收用户上传的知识库或任意 URL。"""

    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        """返回有依据的有限匹配；无法确认时返回空元组。"""
        ...


class ModelPort(Protocol):
    """复用已有 AI 服务的生成能力，禁止业务身份或任意工具调用。"""

    async def answer(self, question: str, context: str) -> ModelAnswer:
        """对审核过的公开资料发起一次非流式请求，不自动重试。"""
        ...
