"""显式校验运行环境；尚未迁移的业务不自动回退到演示数据库。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

Environment = Literal["local", "test", "production"]


@dataclass(frozen=True)
class Settings:
    """组合根使用的配置；交易 simulation 表示模拟支付，并非演示商品。"""

    environment: Environment
    legacy_origin: str | None = None
    assistant_origin: str | None = None
    assistant_token: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """兼容适配目前只允许显式本机 HTTP 源站，不接受远程、凭据或目标路径。"""
        if self.assistant_origin is not None:
            assistant = urlsplit(self.assistant_origin)
            if (
                self.environment == "production"
                or assistant.scheme != "http"
                or assistant.hostname not in ("127.0.0.1", "localhost", "::1")
                or assistant.port is None
                or assistant.port in (8001, 8081, 5173, 4173)
                or assistant.username is not None
                or assistant.password is not None
                or assistant.path not in ("", "/")
                or assistant.query
                or assistant.fragment
                or not self.assistant_token
            ):
                raise ValueError(
                    "FAQ 服务须为显式本机端口并配置 HC_AI_TOKEN，禁止生产启用"
                )
        if self.legacy_origin is None:
            return
        parsed = urlsplit(self.legacy_origin)
        if (
            self.environment == "production"
            or parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.port is None
            or parsed.port == 8001
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "旧业务源站必须是显式本机 HTTP 端口；当前禁止生产启用兼容接入"
            )

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> "Settings":
        """从 HUALI_ENV 读取环境；缺失或拼写错误时明确停止启动。"""
        value = values.get("HUALI_ENV")
        environments: dict[str, Environment] = {
            "local": "local",
            "test": "test",
            "production": "production",
        }
        if value is None or value not in environments:
            raise ValueError("HUALI_ENV 必须显式设置为 local、test 或 production")
        return cls(
            environment=environments[value],
            legacy_origin=values.get("HUALI_LEGACY_ORIGIN") or None,
            assistant_origin=values.get("HC_AI_URL") or None,
            assistant_token=values.get("HC_AI_TOKEN", ""),
        )
