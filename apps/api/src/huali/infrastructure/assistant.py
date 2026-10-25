"""公开 FAQ 的身份、审核知识与已有 AI 服务适配，不直接调用模型供应商。"""

import asyncio
import json
import re
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from huali.infrastructure.legacy import NoRedirect
from huali.modules.compat.ports import LegacyGateway
from huali.modules.support.assistant.ports import Actor, KnowledgeDocument, ModelAnswer
from huali.shared.errors import ApplicationError

DEFAULT_KNOWLEDGE = Path(__file__).resolve().parents[5] / "ai_service/approved_faq.json"


class LegacyIdentity:
    """使用组合根同一旧网关查询身份，不把凭据转发给 AI 服务。"""

    def __init__(self, gateway: LegacyGateway | None) -> None:
        """未装配旧服务时保守失败，不创建假身份或信任客户端账号。"""
        self.gateway = gateway

    async def verify(self, token: str) -> Actor:
        """明确的旧 401 才是失效；超时、坏响应和缺配置返回 503。"""
        if not token or len(token) > 2048:
            raise ApplicationError("UNAUTHENTICATED", "请先登录", 401)
        if self.gateway is None:
            raise ApplicationError("IDENTITY_UNAVAILABLE", "身份服务尚未配置", 503)
        try:
            response = await self.gateway.request("GET", "/api/me", token)
        except ApplicationError as error:
            raise ApplicationError(
                "IDENTITY_UNAVAILABLE", "暂时无法核实登录状态，请稍后重试", 503
            ) from error
        if response.status == 401:
            raise ApplicationError("UNAUTHENTICATED", "登录状态已失效，请重新登录", 401)
        if response.status == 403:
            raise ApplicationError("FORBIDDEN", "当前账号不可使用问答", 403)
        data = response.data
        if not 200 <= response.status < 300 or not isinstance(data, dict):
            raise ApplicationError("IDENTITY_UNAVAILABLE", "身份服务响应异常", 503)
        identifier = data.get("id")
        if type(identifier) is not int or not 0 < identifier <= 9007199254740991:
            raise ApplicationError("IDENTITY_UNAVAILABLE", "身份服务响应异常", 503)
        if "status" in data and data["status"] != "active":
            raise ApplicationError("FORBIDDEN", "当前账号不可使用问答", 403)
        return Actor(str(identifier))


class ApprovedRecord(BaseModel):
    """知识文件的明确白名单字段；不是外部搜索结果或用户上传。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=3000)
    source: str = Field(min_length=1, max_length=300)


def terms(value: str) -> set[str]:
    """按旧知识检索思路提取中文双字词和英文词，只用于已审核公开内容。"""
    result = set(re.findall(r"[a-z0-9_]{2,}", value.lower()))
    for part in re.findall(r"[\u4e00-\u9fff]+", value):
        result.update(part[index : index + 2] for index in range(len(part) - 1))
    return result - {"怎么", "如何", "什么", "可以", "请问", "一下", "我的"}


class ApprovedKnowledge:
    """只载入服务端版本化审核清单，缺文件时保守拒绝而不启用旧全量索引。"""

    def __init__(self, path: Path = DEFAULT_KNOWLEDGE) -> None:
        """固定配置文件路径，不允许请求携带任意知识 URL 或本机文件名。"""
        self.path = path

    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        """有界匹配至多三条资料；来源及版本均来自清单。"""
        try:
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError("审核清单过大")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw = payload["documents"]
            if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
                raise ValueError("审核清单结构不正确")
            documents = [ApprovedRecord.model_validate(record) for record in raw]
            if len({document.document_id for document in documents}) != len(documents):
                raise ValueError("审核清单编号重复")
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
            raise ApplicationError(
                "KNOWLEDGE_UNAVAILABLE", "公开规则暂时无法读取，请稍后重试", 503
            ) from error
        query = terms(question)
        scored = []
        for document in documents:
            title_hits = len(query & terms(document.title))
            body_hits = len(query & terms(document.content))
            # 标题更能说明规则所属主题；只有泛词命中时不把无关规则送入模型。
            score = (title_hits * 2 + body_hits) / max(1, len(query) * 3)
            if score >= 0.22 and (title_hits or body_hits >= 2):
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return tuple(
            KnowledgeDocument(item.document_id, item.title, item.version, item.content)
            for _, item in scored[:3]
        )


class FaqModelResponse(BaseModel):
    """已有服务新增窄入口的实际响应，不接受模型自报 sources 或业务动作。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    answer_text: str = Field(min_length=1, max_length=2000)
    mode: str


class LocalFaqModel:
    """仅调用已配置本机 AI 的 FAQ 入口，服务凭据与用户会话完全分开。"""

    def __init__(self, origin: str, service_token: str) -> None:
        """参数在 Settings 中校验，认证仅用于内部 AI 服务。"""
        self.origin = origin.rstrip("/")
        self.service_token = service_token

    async def answer(self, question: str, context: str) -> ModelAnswer:
        """发起一次有界非流式请求，断连不重新发送、不降级成假成功。"""
        return await asyncio.to_thread(self._answer, question, context)

    def _answer(self, question: str, context: str) -> ModelAnswer:
        """不使用代理或重定向；请求正文不含用户 ID、Bearer、历史或订单。"""
        request = Request(
            self.origin + "/faq/answer",
            data=json.dumps({"question": question, "context": context}).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.service_token,
            },
            method="POST",
        )
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(
                request, timeout=15
            ) as response:
                raw = response.read(65537)
                if (
                    len(raw) > 65536
                    or "json" not in response.headers.get("Content-Type", "").lower()
                ):
                    raise ValueError("AI 响应不正确")
                data = FaqModelResponse.model_validate_json(raw)
                if data.mode not in ("mock", "llm") or not data.answer_text.strip():
                    raise ValueError("AI 模式或正文不正确")
                return ModelAnswer(
                    data.answer_text.strip(), "mock" if data.mode == "mock" else "llm"
                )
        except (
            HTTPError,
            URLError,
            OSError,
            ValueError,
            ValidationError,
            HTTPException,
        ) as error:
            raise ApplicationError(
                "ASSISTANT_UNAVAILABLE", "问答服务暂时不可用，输入已保留", 503
            ) from error
