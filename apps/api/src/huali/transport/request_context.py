"""为每次请求分配服务端请求编号，覆盖成功和异常响应。"""

import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    """使用原生 ASGI 中间件，避免 BaseHTTPMiddleware 的流式响应限制。"""

    def __init__(self, app: ASGIApp) -> None:
        """保存下游应用；请求之间不共享可变身份或数据库状态。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """生成请求编号，注入 scope.state 及每个 HTTP 响应头。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = secrets.token_hex(16)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_context(message: Message) -> None:
            """在正文发送前设置安全头，输入中的同名请求头不会被信任。"""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self.app(scope, receive, send_with_context)
