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

FALLBACK = '这个问题我暂时无法准确解答，建议提交工单，客服 08:00—20:00 处理。'
TRANSFER_REPLY = '好的，建议提交工单，客服 08:00—20:00 处理。'
GREETING_REPLY = '您好，我是转角客服助手。请问有什么可以帮您？'

TRANSFER_WORDS = (
    '转人工', '人工客服', '找客服', '人工', '真人', '客服在吗',
    '投诉', '差评', '骗子', '骗人', '气死', '垃圾', '曝光', '12315',
    '强烈不满', '太差', '恶心', '坑人', '退钱', '赔偿',
)
# 带这些词说明是在问「流程」，不是投诉/诉求；「怎么退钱」应回答流程而不是直接转人工。
PROCESS_WORDS = (
    '怎么', '如何', '流程', '多久', '能不能', '可以吗', '步骤', '怎样',
    '什么', '哪里', '为什么',
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


AI_PERMISSIONS = [
    {'cap': '客服页 AI 宠物（提问）', 'user': True, 'support': True, 'admin': True, 'developer': True},
    {'cap': '工单页 AI 建议回复', 'user': False, 'support': True, 'admin': True, 'developer': True},
    {'cap': '查看自己的今日额度', 'user': True, 'support': True, 'admin': True, 'developer': True},
    {'cap': '查看全部用量与来源统计', 'user': False, 'support': False, 'admin': True, 'developer': True},
    {'cap': '开启/关闭 AI、调整每日额度', 'user': False, 'support': False, 'admin': True, 'developer': True},
    {'cap': '重载知识库（本地）', 'user': False, 'support': False, 'admin': True, 'developer': True},
    {'cap': '修改模型/接口地址/API Key', 'user': False, 'support': False, 'admin': False, 'developer': True},
]

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
这个问题我暂时无法准确解答，建议提交工单，客服 08:00—20:00 处理。

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


def _strip_greetings(q):
    s = q
    for w in GREETING_WORDS:
        s = s.replace(w, '')
    return re.sub(r'[\s，。！？、,.!?~～]+', '', s)


def classify(question):
    q = (question or '').strip().lower()
    has_transfer = any(w in q for w in TRANSFER_WORDS)
    has_process = any(w in q for w in PROCESS_WORDS)
    # 「怎么退钱」「退款要多久」是流程咨询，不该直接转人工；
    # 「我要投诉」「骗子」这种没有流程词的才是投诉/诉求。
    if has_transfer and not has_process:
        return 'transfer'
    rest = _strip_greetings(q)
    # 「你好，怎么退款」不能被当成纯问候：剥掉问候词后还有实质内容就按业务问题处理。
    if len(rest) <= 2 and any(w in q for w in GREETING_WORDS):
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


# 回答里附带的「跳转文字链接」：客户看完规则可以一键去对应页面执行。
# href 用站内 hash 路由，前端直接渲染成 <a href="#...">。
LINK_RULES = (
    (('发布', '三张图', '定价'), [{'label': '去发布闲置', 'href': '#publish'}]),
    (('退款', '售后', '取消订单', '待付款', '付款', '面交', '改时间', '重新上架'),
     [{'label': '去订单处理', 'href': '#orders'}, {'label': '提交工单', 'href': '#support'}]),
    (('密码', '注销', '手机号', '隐私'), [{'label': '去账号与安全', 'href': '#me'}]),
    (('信誉',), [{'label': '查看信誉与申诉', 'href': '#credit'}]),
    (('客服', '人工'), [{'label': '去客服中心', 'href': '#support'}]),
    (('举报',), [{'label': '去社区', 'href': '#community'}]),
    (('支付', '小程序'), [{'label': '去客服中心', 'href': '#support'}]),
)
SUPPORT_LINK = [{'label': '去客服中心提交工单', 'href': '#support'}]


def links_for(title):
    for keys, links in LINK_RULES:
        if any(k in (title or '') for k in keys):
            return links
    return []


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


async def call_api(question, context, env, history=None):
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
            *[h for h in (history or [])
              if h.get('role') in ('user', 'assistant') and h.get('content')],
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


async def ai_answer(question, env, history=None):
    started = time.time()
    q = str(question or '').strip()[:800]
    elapsed = lambda: int((time.time() - started) * 1000)
    if not q:
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'links': [],
                'mode': 'rule', 'latency_ms': 0}

    intent = classify(q)
    if intent == 'greeting':
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'links': [],
                'mode': 'rule', 'latency_ms': elapsed()}
    if intent == 'transfer':
        return {'answer': TRANSFER_REPLY, 'action': 'transfer', 'sources': [], 'links': SUPPORT_LINK,
                'mode': 'rule', 'latency_ms': elapsed()}

    hits = retrieve(q)
    if not hits:
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': [], 'links': SUPPORT_LINK,
                'mode': 'guard', 'latency_ms': elapsed()}

    context = build_context(hits)
    notice = ''
    mode = 'llm'
    text = ''
    try:
        text = await call_api(q, context, env, history)
    except Exception:  # noqa: BLE001 - 供应商 401/429/5xx、超时、Key 失效都降级为摘录
        mode = 'mock'
        notice = 'AI 服务暂时不可用，以下为平台规则原文。'
        text = extractive(hits)

    text = strip_thinking(text)
    links = links_for(hits[0][1]['title'])
    if not text or any(w in text for w in UNCERTAIN_WORDS):
        return {'answer': FALLBACK, 'action': 'transfer', 'sources': sources_of(hits),
                'links': SUPPORT_LINK, 'mode': mode, 'notice': notice, 'latency_ms': elapsed()}

    text = trim(text, 300)
    action = 'transfer' if ('转接人工' in text or '转人工' in text) else 'reply'
    return {'answer': text, 'action': action, 'sources': sources_of(hits), 'links': links,
            'mode': mode, 'notice': notice, 'latency_ms': elapsed()}


class AiSupport:
    async def ai_settings(self):
        await self.db.run('INSERT OR IGNORE INTO ai_settings(id,enabled,daily_limit,staff_daily_limit) VALUES(1,1,30,100)')
        return await self.db.first('SELECT * FROM ai_settings WHERE id=1')

    async def ai_enabled(self):
        s = await self.ai_settings()
        return bool(s and s['enabled']) and bool(getattr(self.env, 'HC_AI_API_KEY', ''))

    async def ai_role(self, uid):
        return await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,)) or 'user'

    async def ai_quota(self, uid, role=None):
        s = await self.ai_settings()
        role = role or await self.ai_role(uid)
        limit = int(s['staff_daily_limit'] if role in STAFF else s['daily_limit'])
        day = time.strftime('%Y-%m-%d', time.gmtime(time.time() + 8 * 3600))
        row = await self.db.first('SELECT count,last_at FROM ai_usage WHERE user_id=? AND day=?', (uid, day))
        if row:
            require(int(row['count'] or 0) < limit, f'今天的 AI 提问次数已用完（{limit} 次），建议提交工单', 429)
            require(time.time() - float(row['last_at'] or 0) >= 2, '问得太快了，请稍等两秒', 429)
        return limit

    async def ai_count(self, uid):
        day = time.strftime('%Y-%m-%d', time.gmtime(time.time() + 8 * 3600))
        await self.db.run(
            'INSERT INTO ai_usage(user_id,day,count,last_at) VALUES(?,?,1,?) '
            'ON CONFLICT(user_id,day) DO UPDATE SET count=count+1,last_at=excluded.last_at',
            (uid, day, time.time()))

    async def ai_usage_summary(self, days=7):
        days = max(1, min(int(days or 7), 90))
        since = time.strftime('%Y-%m-%d', time.gmtime(time.time() - (days - 1) * 86400 + 8 * 3600))
        rows = await self.db.all('SELECT day,SUM(count) count FROM ai_usage WHERE day>=? GROUP BY day ORDER BY day', (since,))
        top = await self.db.all('SELECT a.user_id,u.nickname,SUM(a.count) count FROM ai_usage a LEFT JOIN users u ON u.id=a.user_id WHERE a.day>=? GROUP BY a.user_id ORDER BY count DESC LIMIT 5', (since,))
        return {'since': since,
                'days': [{'day': r['day'], 'count': int(r['count'] or 0)} for r in rows],
                'top': [{'user_id': r['user_id'], 'nickname': r['nickname'], 'count': int(r['count'] or 0)} for r in top],
                'total': sum(int(r['count'] or 0) for r in rows)}

    async def ai_chat(self, request):
        uid = await self.page_user(request)
        require(await self.ai_enabled(), 'AI 客服已关闭，请转人工客服', 503)
        d = await json_body(request)
        question = ValidationMixin.text(d.get('question'), 300, '问题')
        history = []
        raw = d.get('history')
        if isinstance(raw, list):
            for h in raw[-4:]:
                if not isinstance(h, dict):
                    continue
                role = h.get('role')
                content = str(h.get('content') or '').strip()[:300]
                if role in ('user', 'assistant') and content:
                    history.append({'role': role, 'content': content})
        await self.ai_quota(uid)
        result = await ai_answer(question, self.env, history)
        # 只有真正调用模型才计入额度；问候、转人工、无命中不扣次数。
        if result.get('mode') == 'llm':
            await self.ai_count(uid)
        return json_response(result)

    async def ai_reply(self, request):
        uid, role = await self.cf_staff_actor(request)
        require(role in STAFF, '仅客服、管理员或开发者可操作', 403)
        require(await self.ai_enabled(), 'AI 客服已关闭，请转人工客服', 503)
        d = await json_body(request)
        tid = int_param(d, 'ticket_id')
        t = await self.db.first('SELECT id,subject,body FROM tickets WHERE id=?', (tid,))
        require(t, '工单不存在', 404)
        msgs = await self.db.all(
            'SELECT body FROM ticket_messages WHERE ticket_id=? AND internal=0 ORDER BY id DESC LIMIT 6', (tid,))
        question = (str(t['subject']) + ' ' + str(t['body']) + ' ' +
                    ' '.join(str(m['body']) for m in reversed(msgs)))[:2000]
        await self.ai_quota(uid, role)
        result = await ai_answer(question, self.env)
        if result.get('mode') == 'llm':
            await self.ai_count(uid)
        return json_response(result)

    async def ai_admin_get(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True)
        s = await self.ai_settings()
        key = bool(getattr(self.env, 'HC_AI_API_KEY', ''))
        return json_response({
            'settings': {'enabled': bool(s['enabled']), 'daily_limit': int(s['daily_limit']),
                         'staff_daily_limit': int(s['staff_daily_limit']), 'updated_at': s['updated_at']},
            'usage': await self.ai_usage_summary(7),
            'knowledge': {'chunks': len(KNOWLEDGE), 'created': None, 'vector': False,
                          'source': 'app/cloudflare/ai_knowledge.py'},
            'provider': 'api' if key else 'mock',
            'model': getattr(self.env, 'HC_AI_MODEL', 'deepseek-flash'),
            'key_configured': key,
            'reload_supported': False,
            'permissions': AI_PERMISSIONS,
        })

    async def ai_admin_update(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True)
        d = await json_body(request)
        enabled = 1 if d.get('enabled') else 0
        try:
            daily = max(1, min(int(d.get('daily_limit') or 30), 500))
            staff = max(1, min(int(d.get('staff_daily_limit') or 100), 500))
        except (TypeError, ValueError):
            raise DomainError('额度必须是 1—500 的整数', 400) from None
        await self.db.run('INSERT OR IGNORE INTO ai_settings(id,enabled,daily_limit,staff_daily_limit) VALUES(1,1,30,100)')
        await self.db.run('UPDATE ai_settings SET enabled=?,daily_limit=?,staff_daily_limit=?,updated_by=?,updated_at=? WHERE id=1',
                          (enabled, daily, staff, uid, time.time()))
        await self.db.run('INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) VALUES(?,?,?,?,?,?,?)',
                          (uid, 0, 'ai_config', None,
                           f"AI 客服：{'开启' if enabled else '关闭'}；普通用户 {daily}/天，客服 {staff}/天",
                           None, time.time()))
        return await self.ai_admin_get(request)

    async def ai_admin(self, request):
        if request.method == 'POST':
            return await self.ai_admin_update(request)
        return await self.ai_admin_get(request)

    async def ai_reload(self, request):
        await self.cf_staff_actor(request, admin=True)
        raise DomainError('线上知识库随部署更新：改完 FAQ 后重新生成 ai_knowledge.py 并重新部署', 501)

AI_ROUTES = {
    '/api/ai/chat': (('POST',), 'ai_chat'),
    '/api/ai/reply': (('POST',), 'ai_reply'),
    '/api/admin/ai': (('GET', 'POST'), 'ai_admin'),
    '/api/admin/ai/reload': (('POST',), 'ai_reload'),
}
