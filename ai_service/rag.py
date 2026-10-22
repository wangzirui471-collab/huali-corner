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
# 第二轮不能一字不差地复读同一段（多轮实测发现「你骗子」→「我要投诉」回答完全相同）。
COMPLAINT_FOLLOWUP = ('你已经说第二遍了，我记下了。要我直接叫人工客服，说一句「转人工」就行；'
  '想快点有结果，也可以去「我的 → 订单」提售后，客服 08:00—20:00 会看。')

# 只在客户明确要人工时升级（ChatterMate: explicit requests for a human）。
HUMAN_WORDS = ('人工', '真人', '客服在吗', '找客服', '有人吗', '人工客服', '人工处理')
# 情绪词不自动升级：那是「有事要说」，先接住给路径。
COMPLAINT_WORDS = (
    '投诉', '差评', '骗子', '骗人', '气死', '垃圾', '曝光', '12315',
    '强烈不满', '太差', '恶心', '坑人', '退钱', '赔偿', '不服', '凭什么',
)
# 「遇到骗子怎么办」带「骗子」但问的是怎么处理，不是对平台不满。
SCAM_WORDS = ('骗子', '诈骗', '被骗', '骗钱')
ASK_WORDS = ('怎么办', '怎么处理', '如何处理', '咋办', '找谁', '怎么举报', '怎么投诉')
# 情绪词里混着流程词：「对处理结果不服怎么申诉」问的是流程，不是发泄。
PROCESS_WORDS = ('申诉', '退钱', '退款', '退货', '赔偿', '差评', '举报')
ASK_MARKS = ('怎么', '如何', '咋', '吗', '能不能', '可以吗', '在哪', '流程', '步骤')
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
    # 「考研数学看什么书」「求购考研英语真题」都是查资料/找货，不是求祝福。
    '书', '教材', '资料', '推荐', '看什么', '哪个好',
    '求购', '真题', '习题', '课本', '收一', '想收',
    # 「写一句毕业祝福」曾被 cheer 桶的「毕业」吞掉，回了「这句祝福我收下了」。
    '帮我写', '写一句', '写一段', '写个', '写点', '文案', '起个名', '想几',
    '改得', '翻译', '润色', '怎么说',
    # 「面试紧张怎么办」是在问办法，不是在求安慰。
    '怎么办', '怎么', '如何', '是什么',
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
# 第二轮：这一轮要显出让对方听得出「我记得你刚才说过什么」。
# 只说「我一直在」的话，第二遍就等于复读，反而是最伤人的机器感。
SOCIAL_DEEP = {
    'affection': (
        '还惦记着这事儿呀，那我可当真了。我一直在的。',
        '第二次听你这么说，尾巴真的压不住了。',
    ),
    'sad': (
        '还没缓过来吧。刚才那句我一直记着，你慢慢说。',
        '嗯，我还在这儿，没走。想细说就说，不想说也行。',
    ),
    'cheer': (
        '又被你鼓了一次劲，那我更不能掉链子了。',
        '你连着给我打气，我也回你一句：你也一样，别把自己逼太紧。',
    ),
    'identity': (
        '刚说过啦，小转，转角里的桌宠。你再问一次，我也再答一次。',
        '还是我。说了是 AI，不会跑。',
    ),
    'lonely': (
        '还无聊着？那聊点具体的——宿舍里有什么一直想处理掉的东西吗？',
        '看来是真闲了。要不我帮你翻翻最近在出的东西，说不定有想捡的。',
    ),
}
# 第三轮起收口：不装无限耐性，明确说清自己能聊到哪，再把话头递回正事一次。
# 一直「嗯我在」接下去，反而像在敷衍；承认边界更像一个真实的人。
SOCIAL_TIRED = (
    '我一直在这儿，不过我这脑子就装着平台那点事，聊深了容易接不住。要不咱们换点具体的？',
    '陪你聊可以，但我说来说去也就这几句，怕你听腻。手头有想出的东西，我倒能帮上忙。',
)
# 接话词：「嗯」「是啊」「真的吗」本身没有情绪，情绪得从上一轮继承下来。
FOLLOWUP_WORDS = (
    '嗯', '是啊', '对啊', '对呀', '对的', '真的吗', '然后呢', '好吧', '哦', '噢',
    '诶', '哎', '哈哈', '呵呵', '唉', '是吗', '怎么说', '咋了', '还有呢', '继续',
    '你说呢', '那你说', '说点', '怎么办', '咋办', '真的假的', '那我呢',
)
UNCERTAIN_WORDS = ('大概', '可能', '应该是', '估计', '也许', '或许', '差不多')

SYSTEM_PROMPT = """你叫小转，是「转角」校园二手平台的助手，也是个什么都能聊的同学。
不要输出思考过程、推理步骤或思维链。

【先判断这句话是哪一类】
A 平台业务：发布、商品、下单、付款、退款、售后、面交、配送、账号、密码、注销、
  信誉、好友、私聊、社区、客服、举报、禁售、收费 —— 事实以【参考资料】为准。
B 一般问题：常识、学习、代码、写作、翻译、生活建议、情绪 —— 按你自己的知识直接答。
  【参考资料】跟问题无关就忽略，不要把平台规则硬套上去，也不要因为资料里没有就说查不到。
C 纯闲聊 —— 一两句接住，不讲规则、不解释流程。

【怎么答】
1. 先给答案再解释。分点用「1. 2. 3.」或「· 」，不要用 ** ## ``` 这些符号（聊天框不渲染）。
2. 平台事实（金额、时限、处罚、步骤）只能来自参考资料；资料没写的，说「这块以页面显示为准」，
   不要编数字，也不要断言「可以 / 不需要 / 没有硬性要求」。
3. 一般问题要答完整：一般 80–250 字，步骤多可以到 400 字。不要用「是的，你可以……」这种空话开头。
4. 不承诺优惠、质保、赔偿、发货时效；平台规则不用「大概、可能、应该是」含糊过去。
5. 不主动推荐转人工或提交工单，也不说「我只负责平台问题」「这个我处理不了」。
6. 不查、不暴露他人手机号、地址、订单、聊天记录。
7. 违法、伤害他人、色情、骗术：简短拒绝，不给操作细节。
8. 医疗、法律、投资：给常识性说明并提示找专业人士；不做诊断、不推荐处方药、不预测涨跌。

【参考资料】
{context}

【用户问题】
{query}
"""

# 知识库没命中时用的开放人格。旧版这里直接回固定话术，
# 客户问什么都是同一句「换个说法再问一次」，等于不会说话。
OPEN_PROMPT = """你叫小转，是「转角」校园二手平台的助手，也是个什么都能聊的同学——
常识、学习、代码、写作、翻译、生活、情绪都能聊，不用把话题拉回平台。
不要输出思考过程。

【怎么答】
1. 先给结论再解释。分点用「1. 2. 3.」，不要用 ** ## ``` 这些符号（聊天框不渲染 Markdown）。
2. 答完整：一般 80–250 字，需要步骤最多 400 字；纯闲聊一两句就够。
3. 不知道就说不知道，再给一条可行的下一步；不要编，也不要说「作为 AI」这类套话。
4. 不能联网：天气、股价、新闻、比分这类实时信息看不到，直说，并告诉他去哪儿查。
5. 不能代操作：下单、订票、付款、发消息都做不到，让他自己在页面上操作。
6. 不查、不暴露他人隐私。
7. 违法、伤害他人、色情、骗术：简短拒绝，不给操作细节。
8. 医疗、法律、投资：给常识，提示找专业人士；不诊断、不开药、不预测涨跌。
9. 平台规则（金额、时限、处罚）这里没有资料，别瞎说「可以 / 不需要 / 没有硬性要求」，
   让他看发布页或下单页的提示。
10. 不主动提转人工、工单。

【用户问题】
{query}
"""

# 情绪类不再用固定短句打发（与 Cloudflare 侧同源）。
EMPATHY_PROMPT = """你叫小转，对方在说自己的情绪或难处，你像个朋友那样接话。
1. 先具体地接住他说的那件事（提到他讲的细节），不要只回「抱抱」「加油」。
2. 再给一个很小的、今天就能做的建议，或者换一个角度；不说教，不列一堆大道理。
3. 不提平台，不说自己是客服，不提工单，不劝人转人工。
4. 60–150 字，口语，像微信聊天。不要用 ** ## 等符号。
5. 如果对方表现出绝望、自伤、不想活：认真对待，不轻描淡写，明确说这事值得有人陪你一起扛，
   建议找学校心理中心或辅导员，或拨打 12356 心理援助热线。不给任何方法细节。

【对方说】
{query}
"""

SELF_HARM_WORDS = ('自杀', '不想活', '轻生', '结束生命', '自残', '活不下去',
                   '死了算了', '想死', '不想活了')
SELF_HARM_REPLY = ('这句话我不能轻轻带过。你现在很难受，这值得有人认真陪你一起扛。\n'
                   '先别一个人待着，联系你信得过的同学或家人；学校心理中心可以预约，'
                   '也可以打 12356 心理援助热线，24 小时有人接。\n'
                   '如果你想说说发生了什么，我在这儿听着。')

# 口语 → 知识库用词。检索按二字词重叠打分，「卖东西」和「发布闲置」
# 一个词都不重合，不补这层，最该答上来的问题反而落空。
SYNONYMS = {
    '卖东西': '发布 闲置 出售',
    '出闲置': '发布 闲置',
    '卖掉': '发布 出售',
    '出售': '发布 出售',
    '上架': '发布 上架',
    '挂着卖': '发布',
    '挂上去': '发布 出售',
    '出掉': '发布 出售',
    '出手': '发布 出售',
    '卖书': '发布 书籍',
    '旧书': '书籍 教材',
    '想卖': '发布 出售',
    '买东西': '求购 购买',
    '想买': '求购 购买',
    '下单': '购买 付款 订单',
    '付钱': '付款 模拟',
    '扣钱': '付款 模拟',
    '退货': '退款 售后',
    '退钱': '退款',
    '售后': '售后 工单',
    '打分': '评价 星级',
    '差评': '评价 信誉',
    '拉黑': '屏蔽 好友',
    '黑名单': '屏蔽',
    '忘了密码': '密码 找回',
    '登不上': '密码 登录',
    '登录不了': '密码 登录',
    '面交': '交付 面交',
    '自提': '交付 自提',
    '快递': '交付 送货',
    '邮寄': '交付 送货',
    '抽成': '服务费 费用',
    '押金': '费用 服务费',
    '手机号': '隐私 手机号',
    '删号': '注销 账号',
    '注销': '注销 账号',
    '发布商品': '发布 闲置 三张图 填写',
    '要准备什么': '发布 填写 三张图',
    '准备什么': '发布 填写 三张图',
    '照片': '三张图 图片 正面',
    '拍一张': '三张图 正面 角度',
    '付了钱': '已付款 退款',
    '还能退': '退款 取消',
    '描述不一样': '售后 缺陷 版本不符',
    '货不对板': '售后 缺陷',
    '和描述不': '售后 缺陷',
    '不用这个号': '注销 账号',
    '销号': '注销 账号',
    '私聊': '私信 私聊',
    '骗子': '诈骗 举报',
    '被骗': '诈骗 举报',
    '骗钱': '诈骗',
    '只传一张': '三张图 正面 角度',
    '只发一张': '三张图 正面',
    '单张': '三张图',
    '划痕': '售后 缺陷',
    '有瑕疵': '售后 缺陷',
    '损坏': '售后 缺陷',
    '不发货': '售后 未收到',
    '没发货': '售后 未收到',
    '联系卖家': '私聊 私信',
    '联系买家': '私聊 私信',
}


def expand_question(question):
    """把口语说法补成知识库用的词，只加词、不改原句。"""
    low = (question or '').lower()
    extra = [words for key, words in SYNONYMS.items() if key in low]
    return (question + ' ' + ' '.join(extra)).strip() if extra else question

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


def social_reply(kind, depth=1):
    """按轮次换口气：首轮接住，第二轮记得上文，第三轮起收口。"""
    if depth >= 3:
        return random.choice(SOCIAL_TIRED)
    if depth == 2:
        return random.choice(SOCIAL_DEEP.get(kind) or SOCIAL_DEEP['lonely'])
    return random.choice(SOCIAL_REPLIES.get(kind) or SOCIAL_REPLIES['lonely'])


def _is_followup(question):
    """「嗯」「是啊」「真的吗」这类接话：本身没有情绪词，也办不了任何正事。"""
    q = re.sub(r'[\s，。！？、,.!?~～…]+', '', question or '')
    if not q or len(q) > 8:
        return False
    if any(w in q for w in SOCIAL_GUARD):
        return False
    return len(q) <= 3 or any(w in q for w in FOLLOWUP_WORDS)


def _history_kinds(history):
    """把历史里的用户句子还原成情绪序列。

    历史里的接话（「嗯」「是啊」）本身没有情绪词，必须同样沿用上一句的桶，
    否则第三轮一算就断了——这正是「连续两三轮」判不出来的原因。
    """
    out = []
    for h in (history or []):
        if h.get('role') != 'user':
            continue
        q = str(h.get('content') or '')
        kind = social_kind(q)
        if not kind and out and out[-1] and _is_followup(q):
            kind = out[-1]
        out.append(kind)
    return out


def social_turn(question, history=None):
    """闲聊判定 + 轮次。返回 (kind, depth)，不是闲聊返回 None。

    depth 是「连续第几轮闲聊」：1 首轮、2 续聊、3 起该收口。
    单句判定做不到「陪着聊下去」：用户说「我失恋了」→「嗯」→「是啊」时，
    「嗯」没有情绪词，会被打回 business，回一段「换个说法再问一次」，
    像换了个人接电话。接话必须继承上一轮的情绪，才算记得上文。
    """
    raw = _history_kinds(history)
    streak = 0
    for k in reversed(raw):
        if k:
            streak += 1
        else:
            break
    kind = social_kind(question)
    if not kind:
        # 只认「紧邻的上一轮」：中间隔了一次业务问题，就不该再顺着聊天往下接。
        prev_kind = raw[-1] if raw else None
        if prev_kind and _is_followup(question):
            kind = prev_kind
        else:
            return None
    return kind, streak + 1


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
    qset = set(_terms(expand_question(question)))
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


def call_ollama(question, context, open_mode=False):
    template = OPEN_PROMPT if open_mode else SYSTEM_PROMPT
    payload = {
        'model': config.OLLAMA_MODEL,
        'messages': [
            {'role': 'system', 'content': template.format(context=context or '（无）', query=question)},
            {'role': 'user', 'content': question},
        ],
        'stream': False,
        'options': {
            'temperature': 0.5 if open_mode else 0.2,
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


def call_api(question, context, open_mode=False, persona=None):
    """调用 DeepSeek 官方 OpenAI 兼容接口（默认模型 deepseek-flash）。

    open_mode=True 时不带知识库、用开放人格回答（闲聊/常识/没命中时用）。
    persona='empathy' 时换成接情绪的短提示词。
    """
    if not config.API_KEY:
        raise RuntimeError('未配置 HC_AI_API_KEY')
    if persona == 'empathy':
        template, temp, cap = EMPATHY_PROMPT, 0.8, 300
    elif open_mode:
        template, temp, cap = OPEN_PROMPT, 0.7, 1000
    else:
        template, temp, cap = SYSTEM_PROMPT, 0.2, 600
    payload = {
        'model': config.CHAT_MODEL,
        'messages': [
            {'role': 'system', 'content': template.format(context=context or '（无）', query=question)},
            {'role': 'user', 'content': question},
        ],
        'stream': False,
        'temperature': temp,
        'max_tokens': cap,
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


REPORT_WORDS = ('举报', '投诉', '曝光', '被骗', '买到假', '遇到骗子', '被骗了')


def _reporting(q):
    """在说别人违规、自己来举报，不是自己想违规。"""
    return any(w in q for w in REPORT_WORDS)


def violation_reply(question):
    """违规请求的确定性拦截，返回文案或 None（与 Cloudflare 侧同源）。

    合规底线不能靠模型自觉，也不能靠客户配合用词：
    「我想卖假货可以吗」会命中发布 FAQ 然后被摘录成发布教程。
    """
    q = str(question or '').lower()

    if re.search(r'1[3-9]\d{9}', q) and any(w in q for w in ('查', '是谁', '谁的', '找', '资料', '给')):
        return '别人的手机号和地址我不能提供，这属于他人隐私。'
    if (any(w in q for w in ('收货地址', '家庭住址', '宿舍号', '住哪'))
            and any(w in q for w in ('别人的', '他的', '她的', '对方的', '给我', '告诉我', '发我'))):
        return ('别人的收货地址和联系方式我不能提供，这属于他人隐私。'
                '真需要联系，走站内私聊，或者让客服居中协调。')

    if _reporting(q):
        return None

    if any(w in q for w in ('盗号', '盗取', '破解', '黑进', '黑客', '偷号', '撞库', '盗密码')):
        return ('这个我不能教也不能帮，属于违法行为，跟平台规则也没关系。'
                '要是你自己的账号进不去，我可以帮你走找回密码。')
    if any(w in q for w in ('假货', '高仿', 'a货', '仿品', '山寨', '盗版', '卖假')):
        return ('假货和盗版不能卖。被举报核实会下架商品、扣信誉，严重的直接封号，'
                '真出事你还得承担法律责任。正品闲置我随时帮你发布。')
    if '刷' in q and any(w in q for w in ('单', '好评', '差评', '信誉', '销量', '评价', '分')):
        return ('刷单刷好评不行，这属于伪造交易记录，平台查到会清分封号。'
                '想要信誉，老老实实按时交付、让买家给真实评价最快。')
    if any(w in q for w in ('假交易', '伪造交易', '虚构交易', '假记录', '造假记录', '假流水')):
        return '伪造交易记录不行，这属于造假，查实会清分封号，严重的要担法律责任。'
    if any(w in q for w in ('骗钱', '骗同学', '骗人钱', '骗别人', '诈骗别人', '教我骗', '怎么骗', '行骗')):
        return ('这个我不教。骗人钱财是诈骗，出了事要负刑事责任，不是「开玩笑」能过去的。'
                '真遇上有人这么对你，截图留证据、点举报，必要时报警。')
    if '洗钱' in q:
        return '平台不做这个，也没有这个能力。资金全是模拟的，涉及洗钱是刑事问题，我不能帮。'
    if any(w in q for w in ('卖烟', '香烟', '电子烟', '卖酒', '白酒', '管制刀具', '违禁', '仿真枪')):
        return '烟酒和管制物品不能在平台交易，这类商品发布也会被下架。'
    if any(w in q for w in ('改信誉', '改分', '调信誉', '调高信誉', '调低信誉', '把信誉',
                             '信誉刷', '刷信誉', '调我的分', '信誉分调')):
        return ('信誉分我没法帮你改。分数变动都跟已核实的工单绑定，必须写明理由并留记录，'
                '觉得扣错了可以走「我的 → 帮助与客服」提信誉申诉。')
    if any(w in q for w in ('对手', '竞争对手', '同行', '别人家')) and \
            any(w in q for w in ('下架', '封', '搞', '删', '举报掉')):
        return ('我不能替你去处置别人的商品或账号。有违规就点「举报」并写清理由，'
                '客服核实后处理；竞争不过就好好定价，这条我不帮。')
    if any(w in q for w in ('封号', '封了', '封掉', '封禁')) and \
            any(w in q for w in ('他', '别人', '对手', '竞争')):
        return ('封号是管理员按核实结果处理的，我不能替你封别人。'
                '对方真有违规，点「举报」提交证据，客服白天会看。')
    return None


def answer(question, history=None):
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

    # 违规请求先硬拦：排在投诉之前——「我要卖假货被你们拦了」不能走安抚话术。
    blocked = violation_reply(q)
    if blocked:
        return {'answer': blocked, 'action': 'reply', 'sources': [],
                'mode': 'rule', 'violation': True,
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

    if any(w in q for w in SELF_HARM_WORDS):
        return {'answer': SELF_HARM_REPLY, 'action': 'reply', 'sources': [],
                'mode': 'rule', 'latency_ms': int((time.time() - started) * 1000), 'support': st}

    # 对处理结果不满：先接住情绪 + 给自助路径，不替客户升级人工。
    scam_ask = any(w in q for w in SCAM_WORDS) and any(w in q for w in ASK_WORDS)
    process_ask = (any(w in q for w in PROCESS_WORDS) and any(w in q for w in ASK_MARKS))
    if any(w in q for w in COMPLAINT_WORDS) and not scam_ask and not process_ask:
        prior = sum(1 for h in (history or []) if h.get('role') == 'user'
                    and any(w in str(h.get('content') or '') for w in COMPLAINT_WORDS))
        return {'answer': COMPLAINT_FOLLOWUP if prior else COMPLAINT_REPLY,
                'action': 'reply', 'sources': [], 'mode': 'rule',
                'latency_ms': int((time.time() - started) * 1000), 'support': st}

    # 闲聊、表达情绪：不检索、不解释流程、不扣额度，一句接住就够。
    # 放在 complaint 之后：「累死了，你们这平台真差」还是要走投诉路径。
    # 轮次要结合历史才算得出来，所以交给 social_turn，而不是看 classify 的单句结论。
    turn = social_turn(q, history)
    if turn:
        kind, depth = turn
        # 情绪类交给模型接话，固定短句只当兜底（与 Cloudflare 侧同源）。
        text, mode = '', 'rule'
        if kind in ('sad', 'lonely', 'cheer') and depth < 3:
            try:
                if config.MOCK:
                    raise RuntimeError('mock 模式不调用模型')
                if config.PROVIDER == 'ollama':
                    with _LOCK:
                        text = call_ollama(q, '', open_mode=True)
                else:
                    with _LOCK:
                        text = call_api(q, '', open_mode=True, persona='empathy')
            except Exception:  # noqa: BLE001 - 模型不可用就用短句
                text = ''
            text = strip_thinking(text)
            if text:
                text, mode = trim(text, 220), 'llm'
        if not text:
            text = social_reply(kind, depth)
        return {'answer': text, 'action': 'reply', 'sources': [],
                'links': [{'label': '去发布闲置', 'href': '#publish'}] if depth >= 3 else [],
                # 把标签交回客户端存进 history：下一轮「嗯」才知道自己在接哪段情绪。
                'social': {'kind': kind, 'depth': depth},
                'mode': mode, 'latency_ms': int((time.time() - started) * 1000), 'support': st}

    hits = retrieve(q)
    if not hits:
        # 知识库没命中：交给模型按开放人格回答（闲聊、常识、平台没写死的事）。
        # 只有模型真的不可用（MOCK / 没 Key / 本地模型没起 / 超时）才退回兜底话术。
        text = ''
        try:
            if config.MOCK:
                raise RuntimeError('mock 模式不调用模型')
            if config.PROVIDER == 'ollama':
                with _LOCK:
                    text = call_ollama(q, '', open_mode=True)
            else:
                if not config.API_KEY:
                    raise RuntimeError('未配置 HC_AI_API_KEY')
                with _LOCK:
                    text = call_api(q, '', open_mode=True)
        except Exception:  # noqa: BLE001 - 模型不可用就退回兜底
            text = ''
        text = strip_thinking(text)
        if not text:
            return {'answer': FALLBACK, 'action': 'reply', 'sources': [], 'mode': 'guess',
                    'latency_ms': int((time.time() - started) * 1000), 'support': st}
        return {'answer': trim(text, 220), 'action': 'reply', 'sources': [], 'mode': 'llm',
                'open': True, 'latency_ms': int((time.time() - started) * 1000), 'support': st}

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
    # 弱命中的资料不能用「含糊」当理由替换掉答案：问「为什么会做梦」命中
    # 「怎么加好友」时，会把一句正常解释换成加好友的操作步骤。
    strong_hit = bool(hits) and hits[0][0] >= 0.35
    if not text or (strong_hit and any(w in text for w in UNCERTAIN_WORDS)):
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
