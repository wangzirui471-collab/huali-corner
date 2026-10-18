"""Workers 侧的 HTTP 基础件。

只做三件事：把请求解析成普通 Python 值、把领域异常翻译成 HTTP 状态、统一 JSON 输出。
业务规则不写在这里。
"""
import json
from urllib.parse import parse_qs, urlsplit

from ..core.errors import DomainError
from workers import Response

JSON_HEADERS = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
}

MAX_BODY = 8 * 1024 * 1024
AVATAR_BODY = 4 * ((2 * 1024 * 1024 + 2) // 3)


class ApiError(DomainError):
    """带 HTTP 状态的业务错误。复用 DomainError 的 (message, status) 形状。"""


def json_response(payload, status=200, extra_headers=None):
    headers = dict(JSON_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return Response.from_json(payload, status=status, headers=headers)


def error_response(message, status=400):
    return json_response({'error': message}, status=status)


def query_of(request):
    return {key: values[0] for key, values in parse_qs(urlsplit(request.url).query).items()}


def path_of(request):
    return urlsplit(request.url).path


async def json_body(request):
    """读 JSON 请求体。大小上限与旧服务保持一致（8 MiB）。"""
    text = await request.text()
    if not text:
        raise ApiError('请求过大或为空', 413)
    if len(text.encode('utf-8')) > MAX_BODY:
        raise ApiError('请求过大或为空', 413)
    try:
        data = json.loads(text)
    except ValueError:
        raise ApiError('无效JSON', 400) from None
    if not isinstance(data, dict):
        raise ApiError('请求需为对象', 400)
    return data


def int_param(query, name, required=True):
    raw = query.get(name)
    if raw in (None, ''):
        if required:
            raise ApiError(f'缺少参数 {name}', 400)
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ApiError(f'参数 {name} 不合法', 400) from None


def require(condition, message, status=400):
    if not condition:
        raise ApiError(message, status)


async def guard(handler):
    """把 DomainError 翻译成对应状态码，其余异常一律 500 且不外泄细节。"""
    try:
        return await handler()
    except DomainError as exc:
        return error_response(str(exc), getattr(exc, 'status', 400))
    except Exception:  # noqa: BLE001 - 边界处兜底，绝不回传堆栈
        return error_response('服务内部错误', 500)
