"""本地 RAG：检索知识库 -> 只依据资料生成客服回答。

行为严格按企业客服 Agent 流程：
  问候/闲聊 -> 直接短回复
  转人工/投诉/强烈不满 -> 直接转接
  业务问题 -> 检索；检索不到或资料不足 -> 固定兜底话术转人工
生成模型只允许使用检索到的资料，不允许用模型自带知识补全。
"""
import json
import math
import re
import threading
import time
import urllib.request

import config
from ingest import ollama_embed, tokenize

FALLBACK = '这个问题我暂时无法为您准确解答，马上帮您转接人工客服。'
TRANSFER_REPLY = '好的，马上为您转接人工客服，请稍等。'
GREETING_REPLY = '您好，我是转角客服助手。请问有什么可以帮您？'

TRANSFER_WORDS = (
    '转人工', '人工客服', '找客服', '人工', '真人', '客服在吗',
    '投诉', '差评', '骗子', '骗人', '气死', '垃圾', '曝光', '12315',
    '强烈不满', '太差', '恶心', '坑人', '退钱', '赔偿',
)
GREETING_WORDS = (
    '你好', '您好', 'hi', 'hello', '在吗', '谢谢', '多谢', '再见', '拜拜',
    '早上好', '晚上好', '下午好',
)
UNCERTAIN_WORDS = ('大概', '可能', '应该是', '估计', '也许', '或许', '差不多')

SYSTEM_PROMPT = """你是一名企业客服 Agent，只服务「转角」校园二手交易平台。
你必须严格按下面的流程工作，不要输出任何思考过程、推理步骤或思维链。

【执行流程】
1. 只允许使用下方【参考资料】中明确写出的信息回答业务问题。
2. 绝对不允许使用你自带的模型知识补充业务事实。
3. 资料没有写到的内容，一律使用固定兜底话术，不要猜测、不要估算。
4. 不承诺优惠、质保、赔偿、发货时效；不使用“大概、可能、应该是”等不确定表述。
5. 回答简短、友好、口语化，适合客户聊天，不超过 200 字；不要用 Markdown、标题或长段落。
6. 不主动拓展无关内容；不查询或暴露他人手机号、聊天记录、订单等隐私。

【固定兜底话术（必须一字不差）】
这个问题我暂时无法为您准确解答，马上帮您转接人工客服。

【参考资料】
{context}

【用户问题】
{query}
"""

# 本地 Ollama 不能走系统代理
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_LOCK = threading.Lock()
_CACHE = {'mtime': 0.0, 'data': None}


def load_index(force=False):
    if not config.INDEX.exists():
        raise RuntimeError('index.json 不存在，请先运行 python ai_service/ingest.py')
    mtime = config.INDEX.stat().st_mtime
    if force or _CACHE['data'] is None or _CACHE['mtime'] != mtime:
        _CACHE['data'] = json.loads(config.INDEX.read_text(encoding='utf-8'))
        _CACHE['mtime'] = mtime
    return _CACHE['data']


def reload_index():
    return load_index(force=True)


def classify(question):
    q = (question or '').strip().lower()
    if any(w in q for w in TRANSFER_WORDS):
        return 'transfer'
    if len(q) <= 24 and any(w in q for w in GREETING_WORDS):
        return 'greeting'
    return 'business'


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# 中文常见二元组：不承载业务含义，留在查询里会把「可以便宜点吗」误判成发布规则
STOP = {
    '怎么', '可以', '什么', '请问', '一下', '这个', '那个', '多少', '如何', '是否',
    '我的', '你的', '我们', '你们', '为什', '么样', '能不', '不能', '是不', '不是',
    '有没', '没有', '的话', '就是', '还是', '然后', '现在', '需要', '一个', '一些',
    '东西', '事情', '这边', '那边', '行不', '好不', '要不', '大概', '可能',
}


def _terms(text):
    return [t for t in tokenize(text) if t not in STOP]


def retrieve(question, k=None):
    idx = load_index()
    k = k or config.TOP_K
    qvec = None
    if idx.get('embed_ok'):
        try:
            qvec = ollama_embed(question)
        except Exception:  # noqa: BLE001 - 查询向量失败就退关键词
            qvec = None
    qset = set(_terms(question))
    if not qset and not qvec:
        return []
    scored = []
    for chunk in idx['chunks']:
        if qvec and chunk.get('vector'):
            score = cosine(qvec, chunk['vector'])
        else:
            ct = set(chunk.get('tokens') or tokenize(chunk['text']))
            tt = set(tokenize(chunk.get('title') or ''))
            # 标题命中权重 2 倍；分母用 2*查询词数，把分数压回 0..1
            overlap = sum(2 if term in tt else 1 for term in qset if term in ct)
            score = overlap / (2 * max(1, len(qset)))
            if question.strip() and question.strip() in chunk['text']:
                score += 0.2
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    threshold = max(config.MIN_SCORE, 0.28) if qvec else max(config.MIN_SCORE, 0.22)
    return [(s, c) for s, c in scored[:k] if s >= threshold]


def build_context(hits):
    lines = []
    for i, (score, chunk) in enumerate(hits, 1):
        lines.append(f'[{i}]（{chunk["title"]}）\n{chunk["text"]}')
    return '\n\n'.join(lines)


def sources_of(hits):
    out, seen = [], set()
    for score, chunk in hits:
        key = (chunk['source'], chunk['title'])
        if key in seen:
            continue
        seen.add(key)
        out.append({'title': chunk['title'], 'source': chunk['source'], 'score': round(score, 3)})
    return out


def strip_thinking(text):
    text = text or ''
    text = re.sub(r'```(?:think|reasoning).*?```', '', text, flags=re.S | re.I)
    text = re.sub(r'<think[^>]*>.*?</think>', '', text, flags=re.S | re.I)
    # R1 有时把推理和答案写在同一段，答案通常在「答案：」之后
    if '答案：' in text:
        text = text.split('答案：', 1)[1]
    text = re.sub(r'^\s*(思考|推理|分析)[:：].*$', '', text, flags=re.M)
    text = re.sub(r'^#+\s*', '', text, flags=re.M)
    text = text.replace('**', '').replace('`', '')
    return text.strip()


def trim(text, limit=320):
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    pos = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
    return (cut[:pos + 1] if pos > 80 else cut) + '…'


def extractive(hits):
    """没有模型时的降级：只摘录最相关的一条，不拼接两条不相关内容。"""
    body = re.sub(r'^#+\s*.*$', '', hits[0][1]['text'], flags=re.M).strip()
    body = re.sub(r'\s+', ' ', body)
    sentences = [s for s in re.split(r'(?<=[。！？])', body) if s.strip()]
    answer = ('根据平台规则：' + ''.join(sentences[:2]).strip()).strip()
    return trim(answer, 260) if len(answer) >= 12 else FALLBACK


def call_ollama(question, context):
    payload = {
        'model': config.OLLAMA_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT.format(context=context, query=question)},
            {'role': 'user', 'content': question},
        ],
        'stream': False,
        'options': {
            'temperature': 0.2,
            'top_p': 0.9,
            'num_ctx': config.NUM_CTX,
            'num_predict': config.NUM_PREDICT,
        },
    }
    req = urllib.request.Request(
        config.OLLAMA + '/api/chat',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with _NO_PROXY.open(req, timeout=config.TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    msg = data.get('message') or {}
    return msg.get('content') or ''


def call_api(question, context):
    """调用 DeepSeek 官方 OpenAI 兼容接口（默认模型 deepseek-flash）。"""
    if not config.API_KEY:
        raise RuntimeError('未配置 HC_AI_API_KEY')
    payload = {
        'model': config.CHAT_MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT.format(context=context, query=question)},
            {'role': 'user', 'content': question},
        ],
        'stream': False,
        'temperature': 0.2,
        'max_tokens': config.NUM_PREDICT,
    }
    req = urllib.request.Request(
        config.API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config.API_KEY},
        method='POST',
    )
    with _NO_PROXY.open(req, timeout=config.TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('API 返回空结果')
    return (choices[0].get('message') or {}).get('content') or ''


def answer(question):
    started = time.time()
    q = str(question or '').strip()[:config.MAX_QUESTION]
    if not q:
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'mode': 'rule', 'latency_ms': 0}

    intent = classify(q)
    if intent == 'greeting':
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000)}
    if intent == 'transfer':
        return {'answer': TRANSFER_REPLY, 'action': 'transfer', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000)}

    hits = retrieve(q)
    if not hits:
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': [], 'mode': 'guard',
                'latency_ms': int((time.time() - started) * 1000)}

    context = build_context(hits)
    notice = ''
    mode = 'llm'
    text = ''
    provider = 'mock' if config.MOCK else config.PROVIDER
    if provider == 'api' and not config.API_KEY:
        provider = 'mock'
        notice = '未配置 DeepSeek API Key（HC_AI_API_KEY），以下为知识库原文摘录。'
    if provider == 'mock':
        mode = 'mock'
        if not notice:
            notice = '当前为知识库摘录模式。'
        text = extractive(hits)
    elif provider == 'ollama':
        try:
            with _LOCK:
                text = call_ollama(q, context)
            mode = 'llm'
        except Exception as exc:  # noqa: BLE001 - 本地模型没起时降级
            mode = 'mock'
            notice = f'本地模型暂不可用（{type(exc).__name__}），以下为知识库原文摘录。'
            text = extractive(hits)
    else:
        try:
            with _LOCK:
                text = call_api(q, context)
            mode = 'llm'
        except Exception as exc:  # noqa: BLE001 - API 失败时降级，不中断客服
            mode = 'mock'
            notice = f'DeepSeek API 暂不可用（{type(exc).__name__}），以下为知识库原文摘录。'
            text = extractive(hits)

    text = strip_thinking(text)
    if not text:
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': sources_of(hits), 'mode': mode,
                'notice': notice, 'latency_ms': int((time.time() - started) * 1000)}

    # 硬性规则：不出现不确定的业务表述；出现就按“无法确认”转人工
    if any(w in text for w in UNCERTAIN_WORDS):
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': sources_of(hits), 'mode': mode,
                'notice': notice, 'latency_ms': int((time.time() - started) * 1000)}

    text = trim(text, 300)
    action = 'transfer' if ('转接人工' in text or '转人工' in text) else 'reply'
    return {
        'answer': text,
        'action': action,
        'sources': sources_of(hits),
        'mode': mode,
        'notice': notice,
        'latency_ms': int((time.time() - started) * 1000),
    }
