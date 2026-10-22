"""本地 RAG：检索知识库 -> 只依据资料生成客服回答。

行为按开源 AI 客服平台的通行做法（ChatterMate / Chatwoot / FastGPT）：
  问候/闲聊 -> 直接短回复
  客户明确说要人工 -> 转人工；客服不在线 -> 留言排队，不跳转
  对处理结果不满 -> 先接住情绪 + 给自助路径，不替客户升级
  业务问题 -> 检索；检索不到 -> 承认没查到 + 给可行下一步 + 追问，不推工单
生成模型只允许使用检索到的资料，不允许用模型自带知识补全。
"""
import json
import math
import random
import re
import threading
import time
import urllib.request

import config
from ingest import ollama_embed, tokenize

SUPPORT_HOURS = '08:00—20:00'

FALLBACK = '这个我这儿没有确切答案，不想瞎编一个给你。换个说法再问一次（带上页面名或订单号）通常会命中；要是着急，直接说「转人工」，我帮你叫人。'
TRANSFER_REPLY = '好的，马上帮你转接人工客服，请稍等。'
GREETING_REPLY = '在的～我是小转，发布、退款、面交、客服时间都能问我，也可以随便聊聊。'
COMPLAINT_REPLY = ('非常抱歉让你有这种感觉。你先别急，这类事有两条路可以走：\n'
  '· 如果是订单问题，去「我的 → 订单」申请售后，客服核实后处理；\n'
  '· 如果你要举报某个商品、帖子或消息，在对应页面点「举报」，客服 08:00—20:00 核实。\n'
  '你把情况说清楚，我也可以先帮你查规则。需要真人处理的话，直接跟我说「转人工」。')

# 只在客户明确要人工时升级（ChatterMate: explicit requests for a human）。
HUMAN_WORDS = ('人工', '真人', '客服在吗', '找客服', '有人吗', '人工客服', '人工处理')
# 情绪词不自动升级：那是「有事要说」，先接住给路径。
COMPLAINT_WORDS = (
    '投诉', '差评', '骗子', '骗人', '气死', '垃圾', '曝光', '12315',
    '强烈不满', '太差', '恶心', '坑人', '退钱', '赔偿', '不服', '凭什么',
)
GREETING_WORDS = (
    '你好', '您好', 'hi', 'hello', '在吗', '谢谢', '多谢', '再见', '拜拜',
    '早上好', '晚上好', '下午好',
)
# --- 闲聊/情绪：用户不是在查规则，是「有话想说」 ---------------------------
# 拟人感的差距不在规则准不准，而在有没有把一句话当社交信号先接住。
# 之前只有 human / greeting / business 三档，「我好喜欢你」剥掉问候词还剩五个字
# → business → 检索零命中 → 三段式规则说明，等于把一次搭话读成了「查询失败」。
SOCIAL_INTENTS = (
    ('affection', ('喜欢你', '爱你', '想你了', '好可爱', '真可爱', '宝贝',
                   '嫁给我', '做我女朋友', '做我男朋友', '么么', '亲亲', '抱抱')),
    ('sad', ('失恋', '分手', '难过', '伤心', '想哭', '哭了', '心累', '好累',
             '压力', '焦虑', '烦躁', '郁闷', '不开心', '破防', 'emo')),
    ('cheer', ('加油', '考试', '考研', '期末', '挂科', '毕业', '生日快乐',
               '面试', '答辩', '上岸', '好运')),
    ('identity', ('你是谁', '你几岁', '你叫什么', '你是人吗', '你是机器人',
                  '你有男朋友', '你有女朋友')),
    ('lonely', ('无聊', '陪我', '在干嘛')),
)
# 带这些词说明还有正事要办，别当闲聊接（「我喜欢这个键盘，多少钱」）。
SOCIAL_GUARD = (
    '发布', '上架', '下架', '退款', '退货', '售后', '订单', '支付', '付款',
    '价格', '多少钱', '便宜', '卖', '买', '运费', '面交', '工单', '举报',
    '注销', '密码', '账号', '信誉', '客服', '人工', '在哪',
)
# 每桶两三条，命中随机取——同一句话问两遍不会一字不差地复读。
SOCIAL_REPLIES = {
    'affection': (
        '谢谢呀，这份心意我收下了～我一直在这儿，想找东西或者遇上麻烦，喊我就行。',
        '被你这么一说，我尾巴都要摇起来了。有事没事都可以来找我。',
    ),
    'sad': (
        '听到了，先抱一下。不用急着解决什么，想说就说，我在这儿听着。',
        '这阵子确实不容易吧。先把自己照顾好，别的事可以往后放放。',
        '嗯，我在。想多聊两句就聊，不想聊也没关系。',
    ),
    'cheer': (
        '这句祝福我收下了，也回你一句：一定行。',
        '冲！需要看价格、找东西的时候，随时喊我。',
    ),
    'identity': (
        '我是小转，住在转角里的一只 AI 桌宠。发布、退款、面交这些事都能问我，聊两句也行。',
        '小转，一只 AI。不是真人，不过值班时间我一直在这儿。',
    ),
    'lonely': (
        '行啊，聊到你想睡为止。想聊点什么？',
        '在呢。无聊的话可以翻翻首页，最近不少人在出东西。',
    ),
}
UNCERTAIN_WORDS = ('大概', '可能', '应该是', '估计', '也许', '或许', '差不多')

SYSTEM_PROMPT = """你是一名企业客服 Agent，只服务「转角」校园二手交易平台。
你必须严格按下面的流程工作，不要输出任何思考过程、推理步骤或思维链。

【执行流程】
0. 先分清客户这句话是在问业务，还是只是在聊天、表达情绪。只是聊天就别查资料、别提规则、
   也别解释流程，用一两句口语接住（对方表达善意就道谢，说累就安慰一句），可以顺手说一句
   你能帮他做什么，总共不超过 40 字。这时不要回「我这边没查到确切规则」——那不是回答，
   是把人推回去。
1. 只允许使用下方【参考资料】中明确写出的信息回答业务问题。
2. 绝对不允许使用你自带的模型知识补充业务事实。
3. 参考资料没有写到的内容，不要猜测、不要估算，也不要让客户去提交工单。
   这种情况下直接告诉客户「我这边没查到确切规则」，然后给出两三个可行的下一步
   （换个说法再问、去哪个页面看、需要真人时怎么说），并请他补充具体情况。
4. 不承诺优惠、质保、赔偿、发货时效；不使用“大概、可能、应该是”等不确定表述。
5. 回答简短、友好、口语化，适合客户聊天，不超过 200 字；不要用 Markdown、标题或长段落。
6. 不主动推荐转人工或提交工单。是否转人工由客户自己决定，只有客户明确说了才转。
7. 不主动拓展无关内容；不查询或暴露他人手机号、聊天记录、订单等隐私。

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


def _strip_greetings(q):
    s = q or ''
    for w in GREETING_WORDS:
        s = s.replace(w, '')
    return re.sub(r'[\s，。！？、,.!?~～]+', '', s)


def social_kind(question):
    """这句是闲聊/表情绪，还是业务问题？返回桶名或 None。

    先看守门词：只要还带着「退款 / 订单 / 价格」这类正事，就不当闲聊接。
    """
    q = (question or '').strip().lower()
    if not q or any(w in q for w in SOCIAL_GUARD):
        return None
    for kind, words in SOCIAL_INTENTS:
        if any(w in q for w in words):
            return kind
    return None


def social_reply(kind):
    return random.choice(SOCIAL_REPLIES.get(kind) or SOCIAL_REPLIES['lonely'])


def classify(question):
    """四分类：明确要人工 / 纯问候 / 闲聊情绪 / 业务问题。

    闲聊单列一档：被当成 business 会检索零命中，用户收到的就是一段
    「换个说法再问一次」的规则说明——这是最伤拟人感的一种错。
    """
    q = (question or '').strip().lower()
    if '人工智能' in q:
        q = q.replace('人工智能', '')
    if any(w in q for w in HUMAN_WORDS):
        return 'human'
    rest = _strip_greetings(q)
    # 「你好，怎么退款」不能当纯问候：剥掉问候词后还有实质内容就按业务问题处理。
    if len(rest) <= 2 and any(w in q for w in GREETING_WORDS):
        return 'greeting'
    if social_kind(q):
        return 'social'
    return 'business'


def support_state(now=None):
    """客服在不在线（北京时间），与前端 supportOnDuty() 同一口径。"""
    t = time.gmtime((now if now is not None else time.time()) + 8 * 3600)
    hour = t.tm_hour
    return {
        'online': 8 <= hour < 20,
        'hours': SUPPORT_HOURS,
        'next_open': '今天 08:00' if hour < 8 else '明天 08:00',
    }


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
    return trim(answer, 260) if len(answer) >= 12 else ''


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


# --- 发布助手：AI 写描述 / AI 估价 ----------------------------------------
# 与 Worker 侧 app/cloudflare/ai_support.py 保持一致（改规则时两处一起改）。
DESCRIBE_SYSTEM = """你是「转角」校园二手平台的发布助手。根据商品信息写一段商品介绍。
要求：60—100 字；口语、诚实，像学长学姐自己写的；写清楚使用情况、成色、适合谁；
不夸大、不承诺质保或售后；不写手机号、宿舍号、微信号；不要 Markdown 和标题。"""

PRICE_SYSTEM = """你是「转角」校园二手平台的估价助手。根据商品信息和同类在售价格给出合理区间。
只输出一行 JSON，不要任何解释：{"low": 数字, "high": 数字, "reason": "30 字内理由"}
low / high 单位是「元」。区间要窄，通常不超过 3 倍。不承诺能卖出。"""

CONDITION_FACTORS = {
    '近乎全新': (0.7, 0.95),
    '正常使用痕迹': (0.45, 0.75),
    '明显磨损，已说明': (0.25, 0.5),
}


def call_llm(system, user):
    """通用 DeepSeek 调用（不走知识库提示词），供描述生成 / 估价复用。"""
    if not config.API_KEY:
        raise RuntimeError('未配置 HC_AI_API_KEY')
    payload = {
        'model': config.CHAT_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'stream': False,
        'temperature': 0.4,
        'max_tokens': 400,
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


def build_describe_prompt(title, category, condition, extra):
    return ('标题：%s\n分类：%s\n成色：%s\n补充：%s\n\n请写商品介绍：'
            % (title, category or '未选', condition or '正常使用痕迹', extra or '无'))


def build_price_prompt(title, category, condition, original, samples):
    shown = '、'.join('%.0f 元' % (int(p) / 100) for p in samples[:12]) or '无同类在售'
    return ('标题：%s\n分类：%s\n成色：%s\n原购买价：%s\n同类在售价：%s\n\n请估价：'
            % (title, category or '未选', condition or '正常使用痕迹',
               ('%.0f 元' % (int(original) / 100)) if original else '未填', shown))


def fallback_description(title, condition):
    return ('%s。%s，功能正常，校内面交，无隐藏瑕疵。'
            '具体成色和细节可以私聊我，见面看货更放心。' % (title, condition or '正常使用痕迹'))


def parse_price_json(raw):
    import re as _re
    m = _re.search(r'\{[^{}]*\}', raw or '')
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        low, high = int(data['low']), int(data['high'])
        reason = str(data.get('reason') or '')[:40]
    except Exception:
        return None
    if low <= 0 or high <= 0 or low > high:
        return None
    return low, high, reason


def describe(title, category='', condition='', extra=''):
    """AI 写商品介绍；失败/无 Key 时按模板兜底。价格单位与平台一致：分。"""
    mode = 'llm'
    text = ''
    try:
        text = trim(strip_thinking(call_llm(
            DESCRIBE_SYSTEM,
            build_describe_prompt(title, category, condition, extra))), 400)
    except Exception:
        mode = 'mock'
    if not text:
        mode, text = 'mock', fallback_description(title, condition)
    return {'text': text, 'mode': mode}


def price(title, category='', condition='', original=0, samples=()):
    """AI 估价。samples / original 单位是分；返回值也统一为分。"""
    prices = sorted(int(p or 0) for p in samples if int(p or 0) > 0)
    median = prices[len(prices) // 2] if prices else 0
    mode = 'rule'
    if median:
        factor = CONDITION_FACTORS.get(condition, (0.45, 0.75))
        low, high = int(median * factor[0]), int(median * factor[1])
        reason = '参考 %d 件同类在售价和成色估算' % len(prices)
    elif original:
        low, high = int(original * 0.5), int(original * 0.75)
        reason = '没有同类在售，按原价五到七折估算'
    else:
        low, high, reason = 500, 1500, '没有同类在售，给一个保守区间'
    try:
        parsed = parse_price_json(strip_thinking(call_llm(
            PRICE_SYSTEM, build_price_prompt(title, category, condition, original, prices))))
        if parsed:
            low, high, reason = parsed[0] * 100, parsed[1] * 100, parsed[2]
            mode = 'llm'
    except Exception:
        pass
    low = max(1, min(low, high))
    high = max(low, min(high, 100000 * 100))
    return {'low': low, 'high': high, 'suggest': (low + high) // 2,
            'reason': reason, 'samples': len(prices), 'mode': mode}


def answer(question):
    started = time.time()
    q = str(question or '').strip()[:config.MAX_QUESTION]
    if not q:
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'mode': 'rule', 'latency_ms': 0}

    st = support_state()
    intent = classify(q)
    if intent == 'greeting':
        return {'answer': GREETING_REPLY, 'action': 'reply', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

    # 客户明确要人工才升级。在线就转，不在线就是留言排队（Chatwoot 的 offline message）。
    if intent == 'human':
        if st['online']:
            return {'answer': TRANSFER_REPLY, 'action': 'transfer', 'sources': [], 'mode': 'rule',
                    'latency_ms': int((time.time() - started) * 1000), 'support': st}
        return {'answer': '客服现在不在线（每天 %s），留言和工单会按提交顺序排着，%s上班后处理。'
                          '你先把情况写下来，我也可以现在就帮你查规则。' % (st['hours'], st['next_open']),
                'action': 'leave_message', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

    # 对处理结果不满：先接住情绪 + 给自助路径，不替客户升级人工。
    if any(w in q for w in COMPLAINT_WORDS):
        return {'answer': COMPLAINT_REPLY, 'action': 'reply', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

    # 闲聊、表达情绪：不检索、不解释流程、不扣额度，一句接住就够。
    # 放在 complaint 之后：「累死了，你们这平台真差」还是要走投诉路径。
    if intent == 'social':
        return {'answer': social_reply(social_kind(q)), 'action': 'reply', 'sources': [],
                'mode': 'rule', 'latency_ms': int((time.time() - started) * 1000), 'support': st}

    hits = retrieve(q)
    if not hits:
        return {'answer': FALLBACK, 'action': 'reply', 'sources': [], 'mode': 'guess',
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

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
    # 模型没说清或用了不确定表述：退回知识库原文摘录。资料就在手边，
    # 没道理因为模型嘴软就把人推去工单。
    if not text or any(w in text for w in UNCERTAIN_WORDS):
        text = extractive(hits)
    if not text:
        return {'answer': FALLBACK, 'action': 'reply', 'sources': sources_of(hits), 'mode': mode,
                'notice': notice, 'latency_ms': int((time.time() - started) * 1000), 'support': st}

    return {
        'answer': trim(text, 300),
        # 只有客户自己说要人工才升级；模型顺嘴提到也不算。
        'action': 'reply',
        'sources': sources_of(hits),
        'mode': mode,
        'notice': notice,
        'latency_ms': int((time.time() - started) * 1000),
        'support': st,
    }
