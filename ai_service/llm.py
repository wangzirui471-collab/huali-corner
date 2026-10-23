"""开源模型网关：把「生成」这一层从客服规则里拆出来。

三种后端共用同一个 chat() 口径：

  ollama   本机 Ollama（默认）——deepseek-r1:7b 就是 DeepSeek-R1-Distill-Qwen-7B
           的 Q4_K_M 量化版，约 4.7GB，8G 显存刚好装得下
  openai   任意 OpenAI 兼容端点（llama.cpp / vLLM / LM Studio），也就是
           自己加载 GGUF 或 safetensors 的路子，不需要 Key
  api      远端 OpenAI 兼容接口（DeepSeek 官方），没配 Key 时上层降级为摘录

消费级显卡的现实约束写在代码里，而不是只写在文档里：

  · 8G 显存跑 7B，并发只会互相拖慢。默认并发 1，排队上限 HC_AI_QUEUE，
    排满立刻抛 ModelBusy，让上层拿知识库原文先顶上，不把请求堆到超时。
  · keep_alive 让模型常驻显存，否则每个问题前都要重新加载 5–15 秒。
  · 显存不够自动降档（14b → 7b → 1.5b），不让人肉试错。
  · R1 先输出  thinking 再输出答案；被 max_tokens 截断时只剩半截推理，
    这种半成品必须当成「没答案」，绝不能当回答发给客户。
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import config

# 本地模型/本机服务不能走系统代理，否则 127.0.0.1 也会被代理成 502。
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

MOCK = 'mock'
OLLAMA = 'ollama'
OPENAI = 'openai'
API = 'api'
LOCAL_KINDS = (OLLAMA, OPENAI)


class ModelError(RuntimeError):
    """模型层错误的基类，上层据此决定降级文案。"""


class ModelBusy(ModelError):
    """排满了：现在问的人比卡能扛的多，过几秒再来。"""

    def __init__(self, retry_after=5, message='模型正忙'):
        super().__init__(message)
        self.retry_after = int(retry_after)


class ModelUnavailable(ModelError):
    """连不上 / 没装模型 / 模型返回空 —— 属于配置或环境问题。"""


# 显存 -> 模型档位。Q4_K_M 权重占用大致是：1.5b ≈ 1.1GB、7b ≈ 4.7GB、14b ≈ 9GB。
# 留 2GB 给 KV cache 和桌面合成，低于门槛就降一档，宁可用小模型也别 OOM。
TIERS = (
    (12.0, 'deepseek-r1:14b'),
    (6.0, 'deepseek-r1:7b'),
    (3.0, 'deepseek-r1:1.5b'),
)
FALLBACK_MODEL = 'deepseek-r1:7b'

_vram_cache = {'at': 0.0, 'value': None}
_tags_cache = {'at': 0.0, 'value': None, 'error': ''}
_state_lock = threading.Lock()
_sem_lock = threading.Lock()
_sem = None
_stats = {'calls': 0, 'ok': 0, 'busy': 0, 'fail': 0, 'last_ms': 0, 'last_error': ''}
# 正在排队的请求数。超过 HC_AI_QUEUE 就不再收，早一点说「忙」比晚一点超时好。
_waiting = {'n': 0}
_wait_lock = threading.Lock()


# --- 后端识别 -------------------------------------------------------------

def _resolve(name):
    name = (name or API).strip().lower()
    if name in ('ollama', 'local', 'selfhost', 'self-hosted'):
        return OLLAMA
    if name in ('openai_local', 'llamacpp', 'llama.cpp', 'vllm', 'lmstudio', 'openai_compatible'):
        return OPENAI
    return API


def provider_kind(owner=False):
    """把配置里的别名收敛成四种后端。

    owner=True 时，若单独配了 HC_AI_OWNER_PROVIDER，L1 的办公草稿走另一条路：
    客户问答在小显卡上跑 7B，批量草稿交给云端强模型，互不抢显存。
    """
    if config.MOCK:
        return MOCK
    if owner and config.OWNER_PROVIDER:
        return _resolve(config.OWNER_PROVIDER)
    return _resolve(config.PROVIDER)


def model():
    """当前实际会加载的模型名。"""
    kind = provider_kind()
    if kind == OLLAMA:
        return auto_model() if config.AUTO_MODEL else config.OLLAMA_MODEL
    if kind == OPENAI:
        return config.LOCAL_MODEL or config.CHAT_MODEL
    return config.CHAT_MODEL


def _is_loopback(url):
    try:
        host = urllib.parse.urlsplit(url or '').hostname or ''
    except ValueError:
        return False
    return host in ('127.0.0.1', 'localhost', '::1', '0.0.0.0')


def is_local():
    """数据是否完全不离开本机（隐私提示据此切换文案）。"""
    kind = provider_kind()
    if kind == OLLAMA:
        return _is_loopback(config.OLLAMA)
    if kind == OPENAI:
        return _is_loopback(config.LOCAL_URL)
    return False


# --- 显卡与模型档位 -------------------------------------------------------

def vram_gb():
    """读取显卡总显存；没有 NVIDIA 显卡或没装驱动时返回 None（不代表不能跑）。"""
    now = time.time()
    if _vram_cache['value'] is not None and now - _vram_cache['at'] < 300:
        return _vram_cache['value']
    value = None
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=4,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if out.returncode == 0 and out.stdout.strip():
            value = round(max(float(x) for x in out.stdout.split()) / 1024.0, 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        value = None
    _vram_cache['value'] = value
    _vram_cache['at'] = now
    return value


def pick_model(vram=None):
    """按显存给档位建议；探不到显存就返回 None，交给配置决定。"""
    vram = vram_gb() if vram is None else vram
    if not vram:
        return None
    for need, name in TIERS:
        if vram >= need:
            return name
    return TIERS[-1][1]


def auto_model():
    """HC_AI_AUTO_MODEL=1 时的模型名：显存探不到就用配置里的。"""
    return pick_model() or config.OLLAMA_MODEL or FALLBACK_MODEL


def model_installed(name=None):
    """Ollama 里有没有这个模型。服务连不上返回 None（未知 ≠ 没装）。"""
    tags = _ollama_tags()
    if tags is None:
        return None
    name = (name or model()).split(':')[0]
    return any((t.split(':')[0] == name) for t in tags)


# --- 并发闸门 -------------------------------------------------------------

def _semaphore():
    global _sem
    with _sem_lock:
        if _sem is None:
            _sem = threading.BoundedSemaphore(max(1, config.MAX_CONCURRENCY))
        return _sem


def configure():
    """配置热切换（测试或改环境变量后）重建闸门与缓存。"""
    global _sem
    with _sem_lock:
        _sem = None
    _vram_cache['value'] = None
    _vram_cache['at'] = 0.0
    _tags_cache['value'] = None
    _tags_cache['at'] = 0.0


def stats():
    with _state_lock:
        out = dict(_stats)
    out['waiting'] = _waiting['n']
    out['concurrency'] = config.MAX_CONCURRENCY
    out['queue'] = config.QUEUE
    return out


def _bump(key, ms=None, error=''):
    with _state_lock:
        _stats[key] = _stats.get(key, 0) + 1
        if ms is not None:
            _stats['last_ms'] = int(ms)
        if error:
            _stats['last_error'] = error


def reset_stats():
    with _state_lock:
        for key in list(_stats):
            _stats[key] = 0 if key != 'last_error' else ''
        _stats['last_ms'] = 0


# --- HTTP 基座 -----------------------------------------------------------

def _post_json(url, payload, timeout, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers=dict({'Content-Type': 'application/json'}, **(headers or {})),
        method='POST',
    )
    with _NO_PROXY.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _get_json(url, timeout=3.0):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with _NO_PROXY.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _ollama_tags():
    """已安装模型列表，缓存 30 秒；连不上返回 None。"""
    now = time.time()
    if _tags_cache['value'] is not None and now - _tags_cache['at'] < 30:
        return _tags_cache['value']
    try:
        data = _get_json(config.OLLAMA + '/api/tags')
        names = [str(m.get('name') or '') for m in (data.get('models') or []) if m.get('name')]
    except Exception as exc:  # noqa: BLE001 - 连不上就是没装/没起，属于可降级状态
        _tags_cache.update(value=None, at=now, error=type(exc).__name__)
        return None
    _tags_cache.update(value=names, at=now, error='')
    return names


def _ollama_loaded():
    """当前是否已有模型在显存里（/api/ps），失败返回 []。"""
    try:
        data = _get_json(config.OLLAMA + '/api/ps')
        return [str(m.get('name') or '') for m in (data.get('models') or []) if m.get('name')]
    except Exception:  # noqa: BLE001
        return []


# --- 生成 ----------------------------------------------------------------

def _ollama_payload(system, user, max_tokens, temperature, model_name, keep_alive, history=()):
    return {
        'model': model_name,
        'messages': [{'role': 'system', 'content': system}]
                    + [dict(role=h['role'], content=h['content']) for h in history]
                    + [{'role': 'user', 'content': user}],
        'stream': False,
        'keep_alive': keep_alive,
        'options': {
            'temperature': temperature,
            'top_p': 0.9,
            'num_ctx': config.NUM_CTX,
            'num_predict': max_tokens,
        },
    }


def _openai_payload(system, user, max_tokens, temperature, model_name, history=()):
    return {
        'model': model_name,
        'messages': [{'role': 'system', 'content': system}]
                    + [dict(role=h['role'], content=h['content']) for h in history]
                    + [{'role': 'user', 'content': user}],
        'stream': False,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }


def _endpoint(kind, owner):
    """后端地址、Key、模型名。owner=True 时用 L1 专用配置（只有 API 后端有区别）。"""
    if kind == OLLAMA:
        return config.OLLAMA + '/api/chat', None, config.OWNER_MODEL if (
            owner and config.OWNER_MODEL and config.OWNER_MODEL != config.CHAT_MODEL) else model()
    if kind == OPENAI:
        return config.LOCAL_URL, config.LOCAL_KEY, (config.LOCAL_MODEL or config.CHAT_MODEL)
    return (config.OWNER_API_URL if owner else config.API_URL,
            config.OWNER_API_KEY if owner else config.API_KEY,
            config.OWNER_MODEL if owner else config.CHAT_MODEL)


def _generate(kind, system, user, max_tokens, temperature, timeout, owner, keep_alive, history=()):
    url, key, model_name = _endpoint(kind, owner)
    if kind == OLLAMA:
        payload = _ollama_payload(system, user, max_tokens, temperature, model_name,
                                  keep_alive, history)
        data = _post_json(url, payload, timeout)
        return ((data.get('message') or {}).get('content') or ''), model_name

    if kind == API and not key:
        raise ModelUnavailable('未配置 HC_AI_API_KEY')
    payload = _openai_payload(system, user, max_tokens, temperature, model_name, history)
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    data = _post_json(url, payload, timeout, headers)
    choices = data.get('choices') or []
    if not choices:
        raise ModelUnavailable('接口返回空结果')
    return ((choices[0].get('message') or {}).get('content') or ''), model_name


def _clean_history(history, limit=4):
    """只留最近几轮对话，且只认 user/assistant 两种角色、纯文本。"""
    out = []
    for item in list(history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = str(item.get('content') or '').strip()
        if role not in ('user', 'assistant') or not content:
            continue
        out.append({'role': role, 'content': content[:300]})
    return out


def chat(system, user, *, max_tokens=None, temperature=0.3, timeout=None,
         owner=False, keep_alive=None, history=None):
    """调模型拿正文。失败抛 ModelBusy / ModelUnavailable，上层据此降级。

    history 是多轮上下文（上一问/上一答），让「那这个多少钱」这种省略句接得上。
    返回已剥掉思考过程的纯文本；模型只吐了半截推理时抛 ModelUnavailable。
    """
    kind = provider_kind(owner)
    if kind == MOCK:
        raise ModelUnavailable('摘录模式不调用模型')

    if max_tokens is None:
        max_tokens = config.NUM_PREDICT
    keep_alive = keep_alive or config.KEEP_ALIVE
    local = kind in LOCAL_KINDS
    if local:
        # 小模型长文本会拖到超时：按输出长度给时间，别用远端 API 的 60 秒硬套。
        max_tokens = min(int(max_tokens), config.LOCAL_MAX_PREDICT)
        if timeout is None:
            timeout = max(config.TIMEOUT, min(240.0, 20.0 + max_tokens * 0.35))
    timeout = timeout or config.TIMEOUT
    turns = _clean_history(history)

    _bump('calls')
    started = time.time()
    gate = _semaphore()
    # 空闲就直接进；不空闲才排队，排队名额用完就立刻说「忙」。
    # 两道闸的门槛都写死在这里，不让请求堆到 HTTP 超时才发现没人接。
    admitted = gate.acquire(blocking=False)
    if not admitted:
        with _wait_lock:
            if _waiting['n'] >= max(0, config.QUEUE):
                _bump('busy')
                raise ModelBusy(config.QUEUE_RETRY_AFTER, '排队已满（上限 %d 个）' % config.QUEUE)
            _waiting['n'] += 1
        try:
            admitted = gate.acquire(timeout=max(0.1, config.QUEUE_TIMEOUT))
        finally:
            with _wait_lock:
                _waiting['n'] -= 1
    if not admitted:
        _bump('busy')
        raise ModelBusy(config.QUEUE_RETRY_AFTER, '排队超时（并发 %d）' % config.MAX_CONCURRENCY)
    try:
        text = ''
        last_exc = None
        # 本地服务偶发 503/连接被拒（首次加载、模型切换）时重试一次，其余不重试：
        # 超时说明卡已经跑满了，再试一次只会让客户多等一倍。
        for attempt in (0, 1):
            try:
                text, model_name = _generate(
                    kind, system, user, max_tokens, temperature, timeout, owner, keep_alive, turns)
                last_exc = None
                break
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if attempt == 0 and exc.code in (500, 502, 503):
                    time.sleep(0.6)
                    continue
                raise
            except urllib.error.URLError as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                raise
    except urllib.error.HTTPError as exc:
        _bump('fail', (time.time() - started) * 1000, 'HTTP %s' % exc.code)
        raise ModelUnavailable('模型接口返回 %s' % exc.code) from None
    except urllib.error.URLError as exc:
        _bump('fail', (time.time() - started) * 1000, type(exc.reason).__name__)
        raise ModelUnavailable('连不上模型服务（%s）' % type(exc.reason).__name__) from None
    except (TimeoutError, OSError) as exc:
        _bump('fail', (time.time() - started) * 1000, type(exc).__name__)
        raise ModelUnavailable('模型超时（%s 秒）' % int(timeout)) from None
    finally:
        gate.release()

    if last_exc is not None:
        _bump('fail', (time.time() - started) * 1000, type(last_exc).__name__)
        raise ModelUnavailable('模型调用失败：%s' % type(last_exc).__name__) from None

    cleaned = strip_thinking(text)
    if not cleaned:
        _bump('fail', (time.time() - started) * 1000, 'empty')
        raise ModelUnavailable('模型没有产出可用回答')
    _bump('ok', (time.time() - started) * 1000)
    return cleaned


def warmup():
    """把模型加载进显存。服务启动时调一次，首个用户就不用等冷加载。"""
    kind = provider_kind()
    if kind != OLLAMA:
        return {'ok': False, 'reason': '只有 Ollama 后端需要预热'}
    started = time.time()
    payload = {
        'model': model(),
        'prompt': '你好',
        'stream': False,
        'keep_alive': config.KEEP_ALIVE,
        'options': {'num_predict': 4, 'num_ctx': 512},
    }
    try:
        _post_json(config.OLLAMA + '/api/generate', payload, max(30.0, config.TIMEOUT))
    except Exception as exc:  # noqa: BLE001 - 预热失败不影响服务启动
        return {'ok': False, 'model': model(), 'reason': type(exc).__name__,
                'ms': int((time.time() - started) * 1000)}
    return {'ok': True, 'model': model(), 'ms': int((time.time() - started) * 1000)}


# --- 思考过程剥离 --------------------------------------------------------

def strip_thinking(text):
    """去掉 R1 的  thinking 段；不完整（被截断）视为没有答案。

    实测最常见的事故：num_predict 用完了，模型还在  thinking 里绕，
    剥完只剩空串。以前这里会返回半截推理，客户看到的就是一堆自我怀疑。
    """
    out = text or ''
    out = re.sub(r'```(?:think|reasoning).*?```', '', out, flags=re.S | re.I)
    opened = re.search(r'<think[^>]*>', out, re.I)
    if opened and not re.search(r'</think\s*>', out, re.I):
        return ''
    out = re.sub(r'<think[^>]*>.*?</think\s*>', '', out, flags=re.S | re.I)
    # 有些量化版不带标签，直接把「思考：」写在正文里
    out = re.sub(r'^\s*(思考|推理|分析|Thinking)[:：].*$', '', out, flags=re.M)
    if '答案：' in out:
        out = out.split('答案：', 1)[1]
    out = re.sub(r'^#+\s*', '', out, flags=re.M)
    out = out.replace('**', '').replace('`', '')
    return out.strip()


# --- 状态 ----------------------------------------------------------------

def status():
    """给 /health 和自检脚本用的运行状态，全部字段都可安全对外（不含 Key）。"""
    kind = provider_kind()
    name = model()
    st = stats()
    info = {
        'provider': kind,
        'model': name,
        'local': is_local(),
        'vram_gb': vram_gb(),
        'suggested_model': pick_model(),
        'concurrency': config.MAX_CONCURRENCY,
        'queue': config.QUEUE,
        'keep_alive': config.KEEP_ALIVE,
        'stats': st,
        'ready': False,
        'loaded': False,
        'installed': None,
        'reason': '',
        'hint': '',
    }
    if kind == MOCK:
        info['reason'] = '摘录模式（HC_AI_MOCK=1），不调用模型'
        return info
    if kind == OLLAMA:
        tags = _ollama_tags()
        if tags is None:
            info['reason'] = '连不上 Ollama（%s）' % config.OLLAMA
            info['hint'] = '安装并启动 Ollama：https://ollama.com/download'
            return info
        info['installed'] = tags
        info['loaded'] = any(t.split(':')[0] == name.split(':')[0] for t in _ollama_loaded())
        installed = model_installed(name)
        if installed is False:
            info['reason'] = '本机没有 %s' % name
            info['hint'] = 'ollama pull %s' % name
            return info
        info['ready'] = True
        return info
    if kind == OPENAI:
        info['ready'] = bool(config.LOCAL_URL)
        if not info['ready']:
            info['reason'] = '未配置 HC_AI_LOCAL_URL'
        return info
    info['ready'] = bool(config.API_KEY)
    if not info['ready']:
        info['reason'] = '未配置 HC_AI_API_KEY'
        info['hint'] = '设置 Key 或改用 HC_AI_PROVIDER=ollama'
    return info


def describe_backend():
    """启动日志用的一行说明。"""
    kind = provider_kind()
    if kind == OLLAMA:
        return 'Ollama %s @ %s' % (model(), config.OLLAMA)
    if kind == OPENAI:
        return 'OpenAI 兼容 %s @ %s' % (model(), config.LOCAL_URL)
    if kind == API:
        return 'DeepSeek API %s' % config.CHAT_MODEL
    return '摘录模式（不调用模型）'


if __name__ == '__main__':
    # 直接运行 = 打印一次后端状态卡片，便于在命令行确认配置有没有生效
    print(json.dumps(status(), ensure_ascii=False, indent=2))
    sys.exit(0 if status()['ready'] else 1)
