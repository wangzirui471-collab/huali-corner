"""本地 AI 客服客户端。

只访问 127.0.0.1 上的 ai_service，不把工单内容发到任何云端。
客服权限、工单归属由 SupportService.ai_reply 校验。
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from ..core.errors import DomainError

# 本地 Ollama/AI 服务不能走系统代理；否则 127.0.0.1 也可能被代理成 502。
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_RATE = {}
_RATE_LOCK = threading.Lock()


def rate_ok(uid, gap=2.0):
    """同一账号两次提问至少间隔 2 秒，避免连点刷模型。"""
    now = time.time()
    with _RATE_LOCK:
        last = _RATE.get(uid, 0)
        if now - last < gap:
            return False
        _RATE[uid] = now
        if len(_RATE) > 1000:
            for key, ts in list(_RATE.items()):
                if now - ts > 3600:
                    _RATE.pop(key, None)
        return True



def enabled():
    return os.environ.get('HC_AI_ENABLED', '1') == '1'


def _url():
    return os.environ.get('HC_AI_URL', 'http://127.0.0.1:8093').rstrip('/')


_PROVIDER = {'at': 0.0, 'value': None}


def provider_info(timeout=1.5):
    """问一下本地 AI 服务用的是哪个后端，前端据此切换隐私提示。

    缓存 30 秒：/api/config 会被每个页面调用，不能每次都去探服务。
    服务没起时按「非本地」处理——这时 AI 本来也用不了。
    """
    now = time.time()
    if _PROVIDER['value'] is not None and now - _PROVIDER['at'] < 30:
        return _PROVIDER['value']
    data = None
    try:
        req = urllib.request.Request(_url() + '/health', method='GET')
        token = os.environ.get('HC_AI_TOKEN', '')
        if token:
            req.add_header('Authorization', 'Bearer ' + token)
        with _NO_PROXY.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:  # noqa: BLE001 - 探不到就按云端口径，宁可多提示
        data = None
    info = {
        'local': bool(data.get('local')) if isinstance(data, dict) else False,
        'provider': str((data or {}).get('provider') or ''),
        'model': str((data or {}).get('model') or ''),
    }
    _PROVIDER.update(at=now, value=info)
    return info


def local():
    """AI 是否跑在本机开源模型上（数据不出本机）。"""
    return bool(provider_info()['local'])


def suggest(question):
    if not enabled():
        raise DomainError('AI 客服未启用', 503)
    payload = json.dumps({'question': question}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        _url() + '/reply',
        data=payload,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    token = os.environ.get('HC_AI_TOKEN', '')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    timeout = float(os.environ.get('HC_AI_TIMEOUT', '120'))
    try:
        with _NO_PROXY.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise DomainError('AI 服务鉴权失败，请检查 HC_AI_TOKEN', 503) from None
        raise DomainError(f'AI 服务返回错误（{exc.code}）', 502) from None
    except Exception:  # noqa: BLE001 - 连不上就是本地服务没起
        raise DomainError('AI 服务未启动：请先运行 python ai_service/server.py', 503) from None
    if not isinstance(data, dict) or not data.get('answer'):
        raise DomainError('AI 服务返回格式不正确', 502)
    return data


def _post(path, payload):
    """POST 到本地 AI 服务，返回解析后的 JSON。"""
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        _url() + path,
        data=body,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    token = os.environ.get('HC_AI_TOKEN', '')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    timeout = float(os.environ.get('HC_AI_TIMEOUT', '120'))
    try:
        with _NO_PROXY.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise DomainError('AI 服务鉴权失败，请检查 HC_AI_TOKEN', 503) from None
        raise DomainError(f'AI 服务返回错误（{exc.code}）', 502) from None
    except Exception:  # noqa: BLE001 - 连不上就是本地服务没起
        raise DomainError('AI 服务未启动：请先运行 python ai_service/server.py', 503) from None


def describe(payload):
    """发布页「AI 帮我写」：把标题/分类/成色发给本地 AI 服务生成介绍。"""
    if not enabled():
        raise DomainError('AI 客服未启用', 503)
    data = _post('/describe', payload)
    if not isinstance(data, dict) or not data.get('text'):
        raise DomainError('AI 服务返回格式不正确', 502)
    return data


def price(payload):
    """发布页「AI 估价」：本地 AI 服务给区间（含同类在售样本）。"""
    if not enabled():
        raise DomainError('AI 客服未启用', 503)
    data = _post('/price', payload)
    if not isinstance(data, dict) or not data.get('low'):
        raise DomainError('AI 服务返回格式不正确', 502)
    return data


def reload_index():
    """让本地 AI 服务重新读取 index.json（改完 FAQ 后不用重启）。"""
    req = urllib.request.Request(
        _url() + '/reload', data=b'{}', method='POST',
        headers={'Content-Type': 'application/json'},
    )
    token = os.environ.get('HC_AI_TOKEN', '')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with _NO_PROXY.open(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:  # noqa: BLE001
        raise DomainError('AI 服务未启动：请先运行 python ai_service/server.py', 503) from None
