"""公开 FAQ 的严格输入与输出合同，拒绝客户端自报身份和上下文。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerInput(BaseModel):
    """同一问题显式重试沿用 UUID；不接受 history、role 或上下文。"""

    model_config = ConfigDict(extra="forbid")
    client_turn_id: UUID
    question: str = Field(min_length=1, max_length=800, strict=True)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        """空白问题不进入身份或模型适配，不回显原始敏感内容。"""
        value = value.strip()
        if not value:
            raise ValueError("请输入公开规则问题")
        return value


class Source(BaseModel):
    """可信来源只由审核清单构造，正文供用户直接核对。"""

    document_id: str
    title: str
    version: str
    content: str


class Handoff(BaseModel):
    """建议人工入口只导航到工单草稿，不表示已创建工单或分配客服。"""

    recommended: bool
    reason: str = ""
    next_path: Literal["/support/new"] = "/support/new"


class AnswerData(BaseModel):
    """问答结果保留轮次，答案、来源和转人工建议均为只读数据。"""

    client_turn_id: str
    answer_text: str
    mode: Literal["mock", "llm", "handoff"]
    sources: list[Source]
    handoff: Handoff
