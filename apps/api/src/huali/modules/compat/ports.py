"""兼容用例只依赖窄请求端口，不导入旧 Market 或数据库实现。"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import JsonValue


@dataclass(frozen=True)
class LegacyResponse:
    """旧接口的状态与已解析 JSON，不携带 Cookie 或任意上游响应头。"""

    status: int
    data: JsonValue
    retry_after: str | None = None


class LegacyGateway(Protocol):
    """由组合根注入唯一旧服务，禁止客户端选择上游。"""

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, JsonValue] | None = None,
    ) -> LegacyResponse:
        """发送一次请求；超时不自动重放写操作，原幂等键必须保留。"""
        ...
