"""登录和订单的兼容用例：身份仍由旧服务核实，事务仍由旧 writer 提交。"""

from urllib.parse import urlsplit

from pydantic import JsonValue

from huali.modules.compat.ports import LegacyGateway
from huali.shared.errors import ApplicationError

# 兼容入口严格白名单，不形成可访问任意旧管理接口的开放代理。
OPERATIONS = frozenset(
    {
        ("GET", "/api/auth/salt"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/me"),
        ("GET", "/api/orders"),
        ("GET", "/api/order"),
        ("POST", "/api/checkout"),
        ("POST", "/api/order/action"),
        ("POST", "/api/order/update"),
        ("POST", "/api/order/change"),
    }
)


class CompatService:
    """只做合同和故障适配，不复制密码、定价、权限或订单状态机。"""

    def __init__(self, gateway: LegacyGateway | None) -> None:
        """未显式配置上游时保留禁用状态，绝不自动创建演示账号或数据库。"""
        self.gateway = gateway

    async def execute(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, JsonValue] | None = None,
    ) -> JsonValue:
        """单次调用唯一旧入口；保留成功 DTO，错误只返回稳定安全文案。"""
        route = urlsplit(path).path
        if (method, route) not in OPERATIONS:
            raise ApplicationError("NOT_FOUND", "兼容操作不存在", 404)
        public = route == "/api/auth/login" or (
            route == "/api/auth/salt" and "?phone=" in path
        )
        if not public and not token:
            raise ApplicationError("UNAUTHENTICATED", "请先登录", 401)
        if self.gateway is None:
            raise ApplicationError(
                "LEGACY_NOT_CONFIGURED", "尚未配置隔离旧业务服务", 503
            )
        response = await self.gateway.request(method, path, token, body)
        if not 200 <= response.status < 300:
            code, message = {
                400: ("LEGACY_REJECTED", "请求未被旧业务规则接受，请核对输入"),
                401: ("UNAUTHENTICATED", "账号凭据或登录状态无效"),
                403: ("FORBIDDEN", "当前账号无权执行此操作"),
                404: ("NOT_FOUND", "业务资源不存在"),
                409: ("LEGACY_CONFLICT", "业务状态已变化，请核对原记录"),
                429: ("RATE_LIMITED", "请求过于频繁，请稍后重试"),
            }.get(
                response.status,
                ("LEGACY_UNAVAILABLE", "旧服务暂时不可用，请核对提交结果"),
            )
            raise ApplicationError(
                code,
                message,
                response.status if 400 <= response.status < 500 else 502,
                retry_after=response.retry_after if response.status == 429 else None,
            )
        data = response.data
        valid = (
            isinstance(data, list) if route == "/api/orders" else isinstance(data, dict)
        )
        if route == "/api/auth/login" and isinstance(data, dict):
            valid = (
                isinstance(data.get("token"), str)
                and bool(data["token"])
                and isinstance(data.get("user"), dict)
            )
        if not valid:
            raise ApplicationError(
                "LEGACY_INVALID_RESPONSE", "旧服务返回格式不正确", 502
            )
        return data
