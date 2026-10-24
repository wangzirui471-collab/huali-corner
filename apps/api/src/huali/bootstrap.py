"""唯一组合根：在这里装配路由、适配器和显式配置。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from huali.infrastructure.legacy import LocalLegacyGateway
from huali.modules.compat.api import create_router
from huali.modules.compat.ports import LegacyGateway
from huali.shared.errors import ApplicationError
from huali.shared.settings import Settings
from huali.transport.contracts import Envelope, HealthData
from huali.transport.errors import (
    application_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from huali.transport.request_context import RequestContextMiddleware


def create_app(
    settings: Settings, *, legacy_gateway: LegacyGateway | None = None
) -> FastAPI:
    """装配健康检查与显式兼容入口；旧服务仍是唯一账号和订单 writer。"""
    app = FastAPI(
        title="华立转角 API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        responses={
            422: {"model": Envelope[None]},
            500: {"model": Envelope[None]},
        },
    )
    app.add_middleware(RequestContextMiddleware)
    gateway = legacy_gateway
    if gateway is None and settings.legacy_origin:
        gateway = LocalLegacyGateway(settings.legacy_origin)
    app.include_router(create_router(gateway))
    # Starlette 注册签名统一接受 Exception；实际分发保证传入所注册的子类。
    # 仅此适配边界缩窄 handler 参数，业务层不使用类型抑制。
    app.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unexpected_error_handler)

    @app.get("/health", include_in_schema=False)
    @app.get("/api/v1/health", response_model=Envelope[HealthData], tags=["ops"])
    async def health(request: Request) -> Envelope[HealthData]:
        """返回进程存活与环境；明确标记业务尚未就绪，避免误切线上流量。"""
        return Envelope[HealthData](
            code="OK",
            message="成功",
            data=HealthData(
                environment=settings.environment, compat_enabled=gateway is not None
            ),
            request_id=request.state.request_id,
        )

    return app
