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
