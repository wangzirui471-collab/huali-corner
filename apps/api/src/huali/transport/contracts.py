"""v1 新协议封套；旧 /api 的数组、数字编号和单位保持旧合同。"""

from typing import Literal

from pydantic import BaseModel, Field

from huali.shared.settings import Environment


class FieldIssue(BaseModel):
    """字段路径和安全展示文案，不回显密码或数据库错误。"""

    path: str
    message: str


class ErrorDetail(BaseModel):
    """失败时附带的结构化信息，暂时只包含字段校验结果。"""

    fields: list[FieldIssue] = Field(default_factory=list)


class Metadata(BaseModel):
    """协议版本与模拟交易标记；后续兼容转换据此选择 mapper。"""

    schema_version: Literal["v1"] = "v1"
    simulation: Literal[True] = True


class Envelope[Data](BaseModel):
    """所有新 v1 API 共用的成功或错误封套。"""

    code: str
    message: str
    data: Data | None = None
    error: ErrorDetail | None = None
    request_id: str
    meta: Metadata = Field(default_factory=Metadata)


class HealthData(BaseModel):
    """健康检查只证明新服务存活，business_ready 不冒充业务迁移已完成。"""

    status: Literal["ok"] = "ok"
    environment: Environment
    business_ready: Literal[False] = False
