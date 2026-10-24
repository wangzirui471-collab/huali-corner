"""将预期错误、校验失败和未知故障转换成统一且不泄密的 v1 响应。"""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from huali.shared.errors import ApplicationError
from huali.transport.contracts import Envelope, ErrorDetail, FieldIssue

logger = logging.getLogger(__name__)


def error_response(
    request: Request,
    code: str,
    message: str,
    status: int,
    fields: list[FieldIssue] | None = None,
) -> JSONResponse:
    """构建错误封套，确保未知异常也带请求编号和禁止缓存的响应头。"""
    request_id = request.state.request_id
    body = Envelope[None](
        code=code,
        message=message,
        error=ErrorDetail(fields=fields or []),
        request_id=request_id,
    )
    return JSONResponse(
        body.model_dump(),
        status_code=status,
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def application_error_handler(
    request: Request, error: ApplicationError
) -> JSONResponse:
    """保留业务稳定错误码，让客户端区分冲突、无权与可修正的字段。"""
    fields = [FieldIssue(path=item.path, message=item.message) for item in error.fields]
    response = error_response(request, error.code, error.message, error.status, fields)
    if (
        error.retry_after
        and error.retry_after.isdigit()
        and len(error.retry_after) <= 6
    ):
        response.headers["Retry-After"] = error.retry_after
    return response


async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    """提取字段位置；不回传 Pydantic 附带的原始输入及内部校验上下文。"""
    fields = [
        FieldIssue(
            path=".".join(str(part) for part in item["loc"]), message="输入格式不正确"
        )
        for item in error.errors()
    ]
    return error_response(request, "VALIDATION_ERROR", "请检查填写内容", 422, fields)


async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    """未知路由和不支持的方法返回 JSON，禁止落入静态首页。"""
    descriptions = {
        404: ("NOT_FOUND", "资源不存在"),
        405: ("METHOD_NOT_ALLOWED", "请求方法不被允许"),
    }
    code, message = descriptions.get(error.status_code, ("HTTP_ERROR", "请求未能完成"))
    response = error_response(request, code, message, error.status_code)
    # Allow / Retry-After 等协议头仍需保留；请求编号和安全头由服务端负责。
    for key, value in (error.headers or {}).items():
        if key.lower() in ("allow", "retry-after", "www-authenticate"):
            response.headers[key] = value
    return response


async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    """未知错误只记录编号和异常类别，不把 SQL、口令或堆栈放入响应。"""
    logger.error(
        "request_failed request_id=%s exception_type=%s",
        request.state.request_id,
        type(error).__name__,
    )
    return error_response(request, "INTERNAL_ERROR", "服务暂时不可用，请稍后重试", 500)
