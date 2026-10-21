"""Cloudflare 侧 AI 客服：本地知识库检索 + 外接 DeepSeek API。

与 ai_service/rag.py 的行为保持一致；Worker 不能 import ai_service，
所以检索/兜底逻辑在这里保留一份（改规则时两处一起改）。
业务事实只来自 ai_knowledge.py（由 ai_service/index.json 生成）。
"""
import json
import re
import time

from ..core.errors import ValidationMixin, DomainError
from .http import json_body, json_response, require, int_param
from .ai_knowledge import KNOWLEDGE

STAFF = ('support', 'admin', 'developer')

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
STOP = {
    '怎么', '可以', '什么', '请问', '一下', '这个', '那个', '多少', '如何', '是否',
    '我的', '你的', '我们', '你们', '为什', '么样', '能不', '不能', '是不', '不是',
    '有没', '没有', '的话', '就是', '还是', '然后', '现在', '需要', '一个', '一些',
    '东西', '事情', '这边', '那边', '行不', '好不', '要不', '大概', '可能',
}

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


def tokenize(text):
    text = (text or '').lower()
    latin = re.findall(r'[a-z0-9_]+', text)
    zh = re.findall(r'[\u4e00-\u9fff]+', text)
    grams = []
    for run in zh:
        grams.extend(run[i:i + 2] for i in range(max(0, len(run) - 1)))
    return latin + grams


_CHUNKS = []
for _c in KNOWLEDGE:
    _CHUNKS.append({
        'title': _c['title'],
        'source': _c['source'],
        'text': _c['text'],
        'tokens': set(tokenize(_c['title'] + ' ' + _c['text'])),
        'title_tokens': set(tokenize(_c['title'])),
    })


def _terms(text):
    return [t for t in tokenize(text) if t not in STOP]


def retrieve(question, k=4):
    qset = set(_terms(question))
    if not qset:
        return []
    scored = []
    for chunk in _CHUNKS:
        overlap = sum(2 if term in chunk['title_tokens'] else 1 for term in qset if term in chunk['tokens'])
        score = overlap / (2 * max(1, len(qset)))
        if question.strip() and question.strip() in chunk['text']:
            score += 0.2
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(s, c) for s, c in scored[:k] if s >= 0.22]


def classify(question):
    q = (question or '').strip().lower()
    if any(w in q for w in TRANSFER_WORDS):
        return 'transfer'
    if len(q) <= 24 and any(w in q for w in GREETING_WORDS):
        return 'greeting'
    return 'business'


def build_context(hits):
    return '\n\n'.join(f'[{i}]（{c["title"]}）\n{c["text"]}' for i, (_s, c) in enumerate(hits, 1))


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
    if '答案：' in text:
        text = text.split('答案：', 1)[1]
    text = re.sub(r'^\s*(思考|推理|分析)[:：].*$', '', text, flags=re.M)
    text = re.sub(r'^#+\s*', '', text, flags=re.M)
    return text.replace('**', '').replace('`', '').strip()


def trim(text, limit=300):
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    pos = max(cut.rfind('。'), cut.rfind('！'), cut.rfind('？'))
    return (cut[:pos + 1] if pos > 80 else cut) + '…'


def extractive(hits):
    body = re.sub(r'^#+\s*.*$', '', hits[0][1]['text'], flags=re.M).strip()
    body = re.sub(r'\s+', ' ', body)
    sentences = [s for s in re.split(r'(?<=[。！？])', body) if s.strip()]
    answer = ('根据平台规则：' + ''.join(sentences[:2]).strip()).strip()
    return trim(answer, 260) if len(answer) >= 12 else FALLBACK


async def call_api(question, context, env):
    """调用 DeepSeek 官方 OpenAI 兼容接口。"""
    api_key = getattr(env, 'HC_AI_API_KEY', '') or ''
    if not api_key:
        raise DomainError('AI 未配置：请在 Worker 设置 HC_AI_API_KEY', 503)
    api_url = getattr(env, 'HC_AI_API_URL', 'https://api.deepseek.com/chat/completions')
    model = getattr(env, 'HC_AI_MODEL', 'deepseek-flash')
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT.format(context=context, query=question)},
            {'role': 'user', 'content': question},
        ],
        'stream': False,
        'temperature': 0.2,
        'max_tokens': 360,
    }
    from workers import fetch
    resp = await fetch(
        api_url,
        method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_key},
        body=json.dumps(payload, ensure_ascii=False),
    )
    text = await resp.text()
    if getattr(resp, 'status', 200) != 200:
        raise DomainError(f'DeepSeek API 返回 {getattr(resp, "status", 500)}', 502)
    data = json.loads(text)
    choices = data.get('choices') or []
    if not choices:
        raise DomainError('DeepSeek API 返回空结果', 502)
    return (choices[0].get('message') or {}).get('content') or ''


async def ai_answer(question, env):
    started = time.time()
    q = str(question or '').strip()[:800]
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
    try:
        text = await call_api(q, context, env)
    except DomainError:
        raise
    except Exception as exc:  # noqa: BLE001 - API 失败时降级，不中断客服
        mode = 'mock'
        notice = f'DeepSeek API 暂不可用（{type(exc).__name__}），以下为知识库原文摘录。'
        text = extractive(hits)

    text = strip_thinking(text)
    if not text:
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': sources_of(hits), 'mode': mode,
                'notice': notice, 'latency_ms': int((time.time() - started) * 1000)}
    if any(w in text for w in UNCERTAIN_WORDS):
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': sources_of(hits), 'mode': mode,
                'notice': notice, 'latency_ms': int((time.time() - started) * 1000)}

    text = trim(text, 300)
    action = 'transfer' if ('转接人工' in text or '转人工' in text) else 'reply'
    return {'answer': text, 'action': action, 'sources': sources_of(hits), 'mode': mode,
            'notice': notice, 'latency_ms': int((time.time() - started) * 1000)}


class AiSupport:
    async def ai_chat(self, request):
        uid = await self.page_user(request)
        d = await json_body(request)
        question = ValidationMixin.text(d.get('question'), 300, '问题')
        await self.ai_quota(uid)
        result = await ai_answer(question, self.env)
        await self.ai_count(uid)
        return json_response(result)

    async def ai_reply(self, request):
        uid, role = await self.cf_staff_actor(request)
        require(role in STAFF, '仅客服、管理员或开发者可操作', 403)
        d = await json_body(request)
        tid = int_param(d, 'ticket_id')
        t = await self.db.first('SELECT id,subject,body FROM tickets WHERE id=?', (tid,))
        require(t, '工单不存在', 404)
        msgs = await self.db.all(
            'SELECT body FROM ticket_messages WHERE ticket_id=? AND internal=0 ORDER BY id DESC LIMIT 6', (tid,))
        question = (str(t['subject']) + ' ' + str(t['body']) + ' ' +
                    ' '.join(str(m['body']) for m in reversed(msgs)))[:2000]
        await self.ai_quota(uid)
        result = await ai_answer(question, self.env)
        await self.ai_count(uid)
        return json_response(result)

    async def ai_quota(self, uid):
        day = time.strftime('%Y-%m-%d', time.gmtime(time.time() + 8 * 3600))
        limit = int(getattr(self.env, 'HC_AI_DAILY_LIMIT', '30') or 30)
        row = await self.db.first('SELECT count,last_at FROM ai_usage WHERE user_id=? AND day=?', (uid, day))
        if row:
            require(row['count'] < limit, f'今天的 AI 提问次数已用完（{limit} 次），请转人工', 429)
            require(time.time() - (row['last_at'] or 0) >= 2, '问得太快了，请稍等两秒', 429)

    async def ai_count(self, uid):
        day = time.strftime('%Y-%m-%d', time.gmtime(time.time() + 8 * 3600))
        await self.db.run(
            'INSERT INTO ai_usage(user_id,day,count,last_at) VALUES(?,?,1,?) '
            'ON CONFLICT(user_id,day) DO UPDATE SET count=count+1,last_at=excluded.last_at',
            (uid, day, time.time()))


AI_ROUTES = {
    '/api/ai/chat': (('POST',), 'ai_chat'),
    '/api/ai/reply': (('POST',), 'ai_reply'),
}
