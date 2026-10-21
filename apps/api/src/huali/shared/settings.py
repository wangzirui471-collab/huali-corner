"""显式校验运行环境；尚未迁移的业务不自动回退到演示数据库。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Environment = Literal["local", "test", "production"]


@dataclass(frozen=True)
class Settings:
    """组合根使用的配置；交易 simulation 表示模拟支付，并非演示商品。"""

    environment: Environment

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
        return cls(environment=environments[value])
