"""显式 /api/v1/compat 路由；数据保留旧 ID、金额分和时间秒，不冒充规范化新 DTO。"""

from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Header, Query, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StrictFloat,
    StrictInt,
    model_validator,
)

from huali.modules.compat.ports import LegacyGateway
from huali.modules.compat.service import CompatService
from huali.shared.errors import ApplicationError
from huali.transport.contracts import Envelope

Identifier = Annotated[StrictInt, Field(gt=0, le=9007199254740991)]
Timestamp = Annotated[StrictInt | StrictFloat, Field(ge=0, allow_inf_nan=False)]


class Input(BaseModel):
    """拒绝隐藏的 user_id、金额和权限字段，不静默吞掉拼错的请求参数。"""

    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    """兼容旧明文口令模式或客户端 KDF 摘要模式，严格二选一。"""

    phone: str = Field(min_length=1, max_length=120)
    password: SecretStr | None = Field(default=None, min_length=1, max_length=128)
    digest: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")

    @model_validator(mode="after")
    def one_credential(self) -> "LoginInput":
        """不允许两种密码模式同时出现，也不在新 API 内改写旧 KDF 强度。"""
        if (self.password is None) == (self.digest is None):
            raise ValueError("必须且只能提供一种密码凭据")
        return self


class CheckoutInput(Input):
    """下单只接收商品、预约和原请求键，价格、卖家与状态均由旧 writer 决定。"""

    product_ids: list[Identifier] = Field(min_length=1, max_length=20)
    key: str = Field(min_length=1, max_length=100)
    delivery: Literal["pickup", "delivery"]
    address: str = Field(default="", max_length=150)
    appointment: Timestamp
    want_id: Identifier | None = None

    @model_validator(mode="after")
    def different_products(self) -> "CheckoutInput":
        """重复商品在调用 writer 前拒绝，不把 bool 或字符串编号转成商品 ID。"""
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("商品不能重复")
        return self


class ActionInput(Input):
    """动作白名单仅选择旧用例；退款仍通过既有售后工单办理。"""

    id: Identifier
    action: Literal[
        "pay",
        "cancel",
        "confirm_schedule",
        "deliver",
        "handover",
        "receive",
        "reschedule",
    ]
    appointment: Timestamp | None = None
    address: str | None = Field(default=None, max_length=150)


class UpdateInput(Input):
    """付款前修改仍由旧服务核验归属、状态与可变字段。"""

    id: Identifier
    appointment: Timestamp
    product_ids: list[Identifier] | None = Field(
        default=None, min_length=1, max_length=20
    )
    delivery: Literal["pickup", "delivery"] | None = None
    address: str | None = Field(default=None, max_length=150)


class ChangeInput(Input):
    """只允许对已有改约作出决定，不接受客户端指定审批人。"""

    id: Identifier
    accept: bool = Field(strict=True)


def create_router(gateway: LegacyGateway | None) -> APIRouter:
    """由组合根传入唯一依赖；每个路由均公开进入生成协议。"""
    router = APIRouter(prefix="/api/v1/compat", tags=["compat-identity-trade"])
    service = CompatService(gateway)

    async def call(
        request: Request,
        method: str,
        path: str,
        body: dict[str, JsonValue] | None = None,
    ) -> Envelope[JsonValue]:
        """校验同源与 Bearer 语法，不转发任意浏览器头；旧服务核验会话及资源归属。"""
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if (
                parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or (
                    parsed.scheme != request.url.scheme
                    or parsed.netloc != request.headers.get("host")
                )
            ):
                raise ApplicationError("FORBIDDEN", "不接受跨站业务请求", 403)
        authorization = request.headers.get("authorization", "")
        token = ""
        if authorization:
            if not authorization.startswith("Bearer "):
                raise ApplicationError("UNAUTHENTICATED", "登录凭据格式无效", 401)
            token = authorization[7:]
            if not token or len(token) > 512 or any(char.isspace() for char in token):
                raise ApplicationError("UNAUTHENTICATED", "登录凭据格式无效", 401)
        data = await service.execute(method, path, token, body)
        return Envelope[JsonValue](
            code="OK", message="成功", data=data, request_id=request.state.request_id
        )

    @router.get("/auth/salt", response_model=Envelope[JsonValue])
    async def password_parameters(
        request: Request,
        phone: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    ) -> Envelope[JsonValue]:
        """原样返回现有盐与 KDF 轮数，不把不存在账号与已存在账号作额外区分。"""
        path = "/api/auth/salt" + (
            "?" + urlencode({"phone": phone}) if phone is not None else ""
        )
        return await call(request, "GET", path)

    @router.post("/auth/login", response_model=Envelope[JsonValue])
    async def login(request: Request, data: LoginInput) -> Envelope[JsonValue]:
        """只把已选择的凭据交给旧登录用例；本模块不保存密码或签发另一套 token。"""
        body: dict[str, JsonValue] = {"phone": data.phone}
        if data.password is not None:
            body["password"] = data.password.get_secret_value()
        else:
            body["digest"] = data.digest
        return await call(request, "POST", "/api/auth/login", body)

    @router.post("/auth/logout", response_model=Envelope[JsonValue])
    async def logout(request: Request) -> Envelope[JsonValue]:
        """撤销原会话，不仅清除本机页面的登录外观。"""
        return await call(request, "POST", "/api/auth/logout", {})

    @router.get("/me", response_model=Envelope[JsonValue])
    async def me(request: Request) -> Envelope[JsonValue]:
        """身份由原会话接口核实，前端缓存的角色不能构成授权。"""
        return await call(request, "GET", "/api/me")

    @router.get("/orders", response_model=Envelope[JsonValue])
    async def orders(request: Request) -> Envelope[JsonValue]:
        """查询当前账号的买卖订单，不增加可指定其他用户的查询参数。"""
        return await call(request, "GET", "/api/orders")

    @router.get("/order", response_model=Envelope[JsonValue])
    async def order(
        request: Request, id: Annotated[int, Query(gt=0, le=9007199254740991)]
    ) -> Envelope[JsonValue]:
        """按编号查询详情，交易方、客服或其他身份的可见范围仍由旧服务核验。"""
        return await call(request, "GET", "/api/order?" + urlencode({"id": id}))

    @router.post("/checkout", response_model=Envelope[JsonValue])
    async def checkout(
        request: Request,
        data: CheckoutInput,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", max_length=100)
        ] = None,
    ) -> Envelope[JsonValue]:
        """原请求键只转发一次；头与正文不一致时拒绝，不在网络异常后自动生成新键。"""
        if idempotency_key is not None and idempotency_key != data.key:
            raise ApplicationError("IDEMPOTENCY_MISMATCH", "请求标识不一致", 409)
        return await call(
            request,
            "POST",
            "/api/checkout",
            data.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/order/action", response_model=Envelope[JsonValue])
    async def order_action(request: Request, data: ActionInput) -> Envelope[JsonValue]:
        """买卖双方动作沿用旧状态机，不根据页面按钮直接改变订单字段。"""
        return await call(
            request,
            "POST",
            "/api/order/action",
            data.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/order/update", response_model=Envelope[JsonValue])
    async def order_update(request: Request, data: UpdateInput) -> Envelope[JsonValue]:
        """提交原字段与原单位，不写新的订单表或账本。"""
        return await call(
            request,
            "POST",
            "/api/order/update",
            data.model_dump(mode="json", exclude_none=True),
        )

    @router.post("/order/change", response_model=Envelope[JsonValue])
    async def order_change(request: Request, data: ChangeInput) -> Envelope[JsonValue]:
        """确认或拒绝已有改约，由原服务校验当前账号和请求状态。"""
        return await call(
            request, "POST", "/api/order/change", data.model_dump(mode="json")
        )

    return router
