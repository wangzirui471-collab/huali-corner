"""只连接显式本机旧服务的适配器；不跟随重定向、不读取系统代理、不重试写入。"""

import asyncio
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import JsonValue, RootModel

from huali.modules.compat.ports import LegacyResponse
from huali.modules.compat.service import OPERATIONS
from huali.shared.errors import ApplicationError

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class LegacyJson(RootModel[JsonValue]):
    """在外部数据边界解析 JSON，避免将未校验的 Any 传进业务用例。"""


class NoRedirect(HTTPRedirectHandler):
    """拒绝重定向，防止 Bearer 或登录摘要被转发到未配置目标。"""

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """任何跳转均保留为错误，不在适配边界外继续请求。"""
        return None


class LocalLegacyGateway:
    """每次请求使用独立 opener，线程之间不共享账号、Cookie 或请求头。"""

    def __init__(self, origin: str) -> None:
        """接收已经由 Settings 校验的本机源站，超时固定为 10 秒。"""
        self.origin = origin.rstrip("/")

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, JsonValue] | None = None,
    ) -> LegacyResponse:
        """将同步 HTTP 放入线程，不阻塞 ASGI；取消不代表旧写入已回滚。"""
        return await asyncio.to_thread(self._request, method, path, token, body)

    def _request(
        self, method: str, path: str, token: str, body: dict[str, JsonValue] | None
    ) -> LegacyResponse:
        """白名单内只发送一次，保留参数化查询和原 JSON 幂等键。"""
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or (method, parsed.path) not in OPERATIONS:
            raise ApplicationError("NOT_FOUND", "兼容操作不存在", 404)
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            headers["Content-Type"] = "application/json"
        request = Request(
            self.origin + path, data=payload, headers=headers, method=method
        )
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            try:
                response = opener.open(request, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if (
                    len(raw) > MAX_RESPONSE_BYTES
                    or "json" not in response.headers.get("Content-Type", "").lower()
                ):
                    raise ApplicationError(
                        "LEGACY_INVALID_RESPONSE", "旧服务响应不正确", 502
                    )
                value = LegacyJson.model_validate_json(raw).root
                return LegacyResponse(
                    response.status, value, response.headers.get("Retry-After")
                )
        except (URLError, OSError, ValueError, HTTPException) as error:
            raise ApplicationError(
                "LEGACY_UNAVAILABLE", "旧服务连接中断；写操作结果需要核对", 502
            ) from error
