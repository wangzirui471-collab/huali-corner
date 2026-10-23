"""工作模式（Cloudflare D1 版）：owner 平台工具台 + ReAct 规划 + 二次确认。

与本地 `app/support/work.py` 是同一套契约（/api/ai/work/* 四个接口、同一份
工具目录、同样的 proposal→confirm 流程），差异只在数据层与提案存储：

- 本地：SQLite 同步事务 + HMAC 一次性令牌（进程内密钥，重启即失效）；
- 线上：D1 异步批处理 + `ai_office_jobs` 表存提案（token 就是作业号），
  确认时在同一个 batch 里复查 owner 身份、作业状态与参数，再执行业务写入。

安全边界（与本地一致，参照 LangGraph HITL）：
- 读工具直接执行，确定性 SQL，不把用户名单/手机号交给模型“编”；
- 写工具只生成 proposal；模型永远不直接写库；
- 手机号默认打码，reveal 看全号并写 pii_view 审计；看聊天记录写 chat_view 审计。
"""
import json
import re
import secrets
import time

from ..core.errors import DomainError, ValidationMixin
from .http import json_body, json_response, require
from .ai_support import (PRODUCT_SYSTEM, call_llm, clean_product_items,
                         demo_photo_for, parse_products_json, strip_thinking)

ROLE_LABELS = {'user': '普通用户', 'support': '客服', 'admin': '平台管理员',
               'developer': '开发者', 'owner': '平台所有者'}
ROLE_RANK = {'user': 0, 'support': 1, 'admin': 2, 'developer': 3, 'owner': 4}
PRODUCT_STATUS = {'available': '在售', 'reserved': '已预留', 'sold': '已售出', 'removed': '已下架'}
ORDER_STATUS = {'pending': '待付款', 'paid': '已付款', 'awaiting_handover': '待交付',
                'awaiting_receipt': '待收货', 'completed': '已完成', 'cancelled': '已取消',
                'refunded': '已退款', 'partial_refunded': '部分退款', 'disputed': '争议中'}
TICKET_STATUS = {'open': '待处理', 'processing': '处理中', 'review': '待复核',
                 'resolved': '已解决', 'rejected': '已驳回'}

# 工具目录：desc/params 会直接给规划器和前端看，写清楚“能做什么、参数是什么”。
# 与本地 TOOLS 保持一致；content_remove 在 D1 上按现有能力只支持帖子/聊天消息。
TOOLS = {
    'overview': {'title': '平台概览', 'risk': 'read', 'desc': '用户/商品/订单/工单总量与 24h 活跃', 'params': {}},
    'users': {'title': '查用户', 'risk': 'read', 'desc': '按昵称/手机号/角色/状态查账号',
              'params': {'q': '昵称或手机号关键词', 'role': 'user/support/admin/developer/owner',
                         'status': 'active/banned/disabled/deactivated', 'limit': '1-50'}},
    'user_detail': {'title': '用户详情', 'risk': 'read', 'desc': '账号资料 + 商品/订单/工单数量与最近记录',
                    'params': {'id': '用户 id', 'reveal': 'true 时显示完整手机号（写审计）'}},
    'products': {'title': '查商品', 'risk': 'read', 'desc': '按标题/分类/状态/卖家查商品',
                 'params': {'q': '标题关键词', 'category': '分类', 'status': 'available/reserved/sold/removed',
                            'seller': '卖家 id', 'limit': '1-50'}},
    'product_detail': {'title': '商品详情', 'risk': 'read', 'desc': '商品 + 卖家 + 相关订单',
                       'params': {'id': '商品 id'}},
    'orders': {'title': '查订单', 'risk': 'read', 'desc': '按状态/买卖家/天数查订单',
               'params': {'status': '订单状态', 'buyer': '买家 id', 'seller': '卖家 id',
                          'days': '最近 N 天', 'limit': '1-50'}},
    'order_detail': {'title': '订单详情', 'risk': 'read', 'desc': '订单条目 + 买卖双方 + 金额',
                     'params': {'id': '订单 id'}},
    'tickets': {'title': '查工单', 'risk': 'read', 'desc': '按状态/类型/关键词查工单',
                'params': {'status': 'open/processing/review/resolved', 'type': 'refund/report/appeal/reschedule/other',
                           'q': '标题/正文关键词', 'limit': '1-50'}},
    'ticket_detail': {'title': '工单详情', 'risk': 'read', 'desc': '工单 + 全部对话（含内部备注）',
                      'params': {'id': '工单 id'}},
    'audit': {'title': '查审计', 'risk': 'read', 'desc': '按操作人/类型/天数查审计记录',
              'params': {'actor': '操作人 id', 'type': '操作类型', 'days': '最近 N 天', 'limit': '1-100'}},
    'stats': {'title': '趋势统计', 'risk': 'read', 'desc': '最近 N 天新增订单/工单与活跃用户',
              'params': {'days': '7 或 30'}},
    'rooms': {'title': '查会话', 'risk': 'read', 'desc': '群聊/私聊/客服会话，含最近消息时间与受理人',
              'params': {'kind': 'group/private', 'support': 'true=只看客服', 'limit': '1-50'}},
    'messages': {'title': '看聊天记录', 'risk': 'read', 'desc': '指定会话的最近消息（会写 chat_view 审计）',
                 'params': {'room': '会话 id', 'limit': '1-50'}},
    'moderation': {'title': '内容治理', 'risk': 'read', 'desc': '待处理举报、被移除的帖子/消息',
                   'params': {'limit': '1-30'}},
    'credit': {'title': '信誉', 'risk': 'read', 'desc': '低信誉用户 + 最近信誉变动',
               'params': {'threshold': '80', 'limit': '1-50'}},
    'offers': {'title': '议价', 'risk': 'read', 'desc': '最近出价/还价记录',
               'params': {'limit': '1-50'}},
    'posts': {'title': '社区内容', 'risk': 'read', 'desc': '按关键词搜帖子/评论',
              'params': {'q': '关键词', 'limit': '1-30'}},
    'ledger': {'title': '资金账本', 'risk': 'read', 'desc': '按类型汇总流水 + 最近记录', 'params': {}},
    'sellers': {'title': '卖家排行', 'risk': 'read', 'desc': '最近 N 天成交额/单量排行',
                'params': {'days': '7/30', 'limit': '1-20'}},
    'demo_generate': {'title': '生成演示商品预览', 'risk': 'read',
                      'desc': '按主题生成演示商品预览（不写入数据库），确认后用 demo_publish 入库',
                      'params': {'prompt': '主题词', 'count': '1-10'}},
    'user_role': {'title': '调整角色', 'risk': 'danger', 'desc': '把某个账号调整为 user/support/admin/developer（不能动 owner）',
                  'params': {'target': '用户 id', 'role': '目标角色'}},
    'user_ban': {'title': '封禁/解封', 'risk': 'danger', 'desc': '封禁或解封账号（含在途订单处置）',
                 'params': {'target': '用户 id', 'banned': 'true/false', 'reason': '理由'}},
    'user_credit': {'title': '调整信誉', 'risk': 'danger', 'desc': '基于已结案工单调整信誉分',
                    'params': {'target': '用户 id', 'delta': '-100..100', 'reason': '依据', 'ticket': '工单 id'}},
    'product_promote': {'title': '平台置顶', 'risk': 'write', 'desc': '把商品置顶 1/3/7 天（模拟支付）',
                        'params': {'id': '商品 id', 'tier': '1d/3d/7d', 'reason': '理由'}},
    'product_batch_delist': {'title': '整店下架', 'risk': 'danger', 'desc': '下架某卖家全部在售商品',
                             'params': {'seller': '卖家 id', 'reason': '理由'}},
    'product_bulk_moderate': {'title': '批量处置商品', 'risk': 'danger',
                              'desc': '按关键词/分类/卖家批量下架或恢复（最多 50 件）',
                              'params': {'q': '标题关键词', 'category': '分类', 'seller': '卖家 id',
                                         'action': 'delist/restore', 'reason': '理由'}},
    'content_remove': {'title': '移除内容', 'risk': 'danger', 'desc': '移除帖子或聊天消息',
                       'params': {'kind': 'post/message', 'id': '内容 id', 'reason': '理由'}},
    'demo_cleanup': {'title': '清理演示商品', 'risk': 'danger', 'desc': '删除所有 virtual 演示商品', 'params': {}},
    'backup': {'title': '创建备份', 'risk': 'write', 'desc': '打包数据库与媒体文件到 R2 backups/', 'params': {}},
    'user_disable': {'title': '注销账号', 'risk': 'danger', 'desc': '注销账号并撤销会话、下架在售商品',
                     'params': {'target': '用户 id'}},
    'user_revoke': {'title': '强制下线', 'risk': 'write', 'desc': '撤销某账号的全部登录会话',
                    'params': {'target': '用户 id'}},
    'product_moderate': {'title': '处置商品', 'risk': 'danger', 'desc': '平台下架/恢复上架商品',
                         'params': {'id': '商品 id', 'action': 'delist/restore', 'reason': '处置理由'}},
    'ticket_reply': {'title': '回复工单', 'risk': 'write', 'desc': '给工单发公开回复或内部备注',
                     'params': {'id': '工单 id', 'body': '回复内容', 'internal': 'true=内部备注'}},
    'ticket_resolve': {'title': '处理工单', 'risk': 'danger', 'desc': '认领/复核/退款/驳回/结案',
                       'params': {'id': '工单 id', 'outcome': 'claim/review/refund/reject/resolved',
                                  'reason': '处理依据', 'amount': '退款金额（分，可选）'}},
    'notification_send': {'title': '发通知', 'risk': 'write', 'desc': '给指定账号发站内通知',
                          'params': {'target': '用户 id', 'body': '通知内容'}},
    'ai_settings': {'title': 'AI 设置', 'risk': 'danger', 'desc': '开关 AI / 调整每日额度',
                    'params': {'enabled': 'true/false', 'daily_limit': '1-500', 'staff_daily_limit': '1-500'}},
    'demo_publish': {'title': '发布演示商品', 'risk': 'write', 'desc': '把预览项批量入库（virtual）',
                     'params': {'items': 'demo_generate 返回的 items'}},
}


def catalog():
    return [{'name': k, 'title': v['title'], 'desc': v['desc'], 'risk': v['risk'],
             'params': v['params']} for k, v in TOOLS.items()]


def _limit(value, default=20, maximum=50):
    try:
        return max(1, min(int(value or default), maximum))
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mask(phone):
    phone = str(phone or '')
    return phone[:3] + '****' + phone[-4:] if len(phone) >= 11 else phone


def _who(args):
    return args.get('nickname') or ('#%s' % args.get('target'))


def _summary(name, args):
    """确认卡上的一句话摘要；批量工具在这里就把规模算出来。"""
    if name == 'user_role':
        return '把「%s」调整为%s，并撤销其登录会话' % (_who(args), ROLE_LABELS.get(args.get('role'), args.get('role')))
    if name == 'user_disable':
        return '注销「%s」，下架其在售商品并撤销会话' % _who(args)
    if name == 'user_revoke':
        return '强制「%s」下线（撤销全部会话）' % _who(args)
    if name == 'user_ban':
        return '%s「%s」' % ('封禁' if args.get('banned') else '解封', _who(args))
    if name == 'user_credit':
        return '把「%s」的信誉分调整 %+d（工单 #%s）' % (_who(args), _int(args.get('delta')), args.get('ticket'))
    if name == 'product_moderate':
        return '%s商品 #%s：%s' % ('恢复' if args.get('action') == 'restore' else '下架',
                                 args.get('id'), args.get('reason'))
    if name == 'product_promote':
        return '把商品 #%s 置顶 %s' % (args.get('id'), args.get('tier'))
    if name == 'product_batch_delist':
        return '下架卖家 #%s 的全部在售商品' % args.get('seller')
    if name == 'product_bulk_moderate':
        verb = '恢复' if args.get('action') == 'restore' else '下架'
        cond = '、'.join('%s=%s' % (k, args.get(k)) for k in ('q', 'category', 'seller') if args.get(k))
        return '按条件批量%s商品（%s，最多 50 件）' % (verb, cond)
    if name == 'content_remove':
        return '移除%s #%s' % ('帖子' if args.get('kind') == 'post' else '聊天消息', args.get('id'))
    if name == 'ticket_reply':
        return '%s工单 #%s' % ('内部备注' if args.get('internal') else '公开回复', args.get('id'))
    if name == 'ticket_resolve':
        return '处理工单 #%s：%s' % (args.get('id'), args.get('outcome'))
    if name == 'notification_send':
        return '给用户 #%s 发通知' % args.get('target')
    if name == 'ai_settings':
        return '调整 AI 设置：%s，普通 %s/天，客服 %s/天' % (
            '开启' if args.get('enabled') else '关闭', args.get('daily_limit'), args.get('staff_daily_limit'))
    if name == 'demo_publish':
        return '批量入库 %d 件演示商品' % len(args.get('items') or [])
    if name == 'demo_cleanup':
        return '删除全部演示商品（virtual）'
    if name == 'backup':
        return '创建一份完整备份（数据库 + 媒体）'
    return name


# --- 账号动作预解析（不调模型，参照本地 office.parse_action）--------------------
_ACCOUNT_PATTERNS = (
    ('role', re.compile(r'把\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?\s*(?:降为|设为|改成|调整为|转为)\s*(管理员|客服|开发者|普通用户|用户)')),
    ('ban', re.compile(r'(?:封禁|禁用)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?')),
    ('disable', re.compile(r'(?:注销|停用)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?')),
    ('revoke', re.compile(r'(?:强制|踢)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?\s*(?:下线|退出)')),
)
_ROLE_WORDS = {'管理员': 'admin', '客服': 'support', '开发者': 'developer',
               '普通用户': 'user', '用户': 'user'}


def account_action(question):
    """从一句话里认出账号动作；只解析，不执行。"""
    q = str(question or '').strip()
    for kind, pattern in _ACCOUNT_PATTERNS:
        m = pattern.search(q)
        if not m:
            continue
        if kind == 'role':
            return {'kind': 'role', 'name': m.group(1), 'role': _ROLE_WORDS[m.group(2)]}
        return {'kind': kind, 'name': m.group(1), 'role': None}
    return None


# --- ReAct 规划器（DSPy 式 few-shot；模型只选工具，不执行）----------------------
WORK_PLAN_SYSTEM = """你是转角平台的工作 Agent 规划器。你处在一个 ReAct 循环里：
根据用户请求、工具目录和已执行步骤，决定下一步调用哪个工具；如果已有结果足够回答，返回 {"tool":"final"}。
只输出 JSON，不要解释、不要 Markdown：{"tool":"users","args":{"q":"小陈"}}

示例（few-shot）：
用户：现在有什么需要我处理的？ → {"tool":"tickets","args":{"status":"open"}}
用户：查一下用户小陈 → {"tool":"users","args":{"q":"小陈"}}
用户：把 godfly 降为客服 → {"tool":"user_role","args":{"target":1,"role":"support"}}
用户：把卖假货的商品全部下架 → {"tool":"product_bulk_moderate","args":{"q":"假货","action":"delist","reason":"平台处置"}}
用户：发布 5 件宿舍好物演示商品 → {"tool":"demo_generate","args":{"prompt":"宿舍好物","count":5}}

规则：
1. 只能选择工具列表里的工具，不能编造；
2. 每次只选一个工具；最多 3 步；已经有足够结果就返回 {"tool":"final"}；
3. 用户只是问数据/列表 → 读工具；要求改账号/处置商品/退款 → 写工具（后端出确认卡，不会直接执行）；
4. 问“待办/需要我处理/待处理” → tickets，status=open；
5. 问订单/成交 → orders；问用户/账号 → users；问商品/在售 → products；问审计 → audit；
6. 问会话/聊天 → rooms；问举报/治理 → moderation；问信誉 → credit；问议价 → offers；
   问帖子/社区 → posts；问账本/流水 → ledger；问卖家/排行 → sellers；
7. 问封禁/解封 → user_ban；问信誉调整 → user_credit；问置顶 → product_promote；
   问整店下架 → product_batch_delist；问批量/全部下架 → product_bulk_moderate；
   问删帖/移除消息 → content_remove；问清理演示商品 → demo_cleanup；问备份 → backup；
8. 要“生成/发布演示商品”→ 先 demo_generate 出预览，再 demo_publish 入库；
9. 只有宽泛地问“平台怎么样/数据概览”才选 overview；
10. 不确定时选 overview。
"""


async def work_plan(question, tools, observations, env):
    """让模型选下一步工具；只做规划，不执行、不碰数据库。"""
    listing = json.dumps(tools or [], ensure_ascii=False)[:8000]
    hist = ''
    if observations:
        hist = '\n已执行步骤（只读结果摘要）：\n' + json.dumps(observations[-4:], ensure_ascii=False)[:4000]
        hist += '\n请决定下一步；若已足够，返回 {"tool":"final"}。'
    model = getattr(env, 'HC_AI_MODEL_OWNER', '') or None
    raw = await call_llm(WORK_PLAN_SYSTEM, '工具列表：%s\n用户请求：%s%s' % (listing, question, hist),
                         env, max_tokens=240, model=model)
    m = re.search(r'\{[\s\S]*\}', strip_thinking(raw) or '')
    if not m:
        raise DomainError('规划结果不是 JSON', 502)
    data = json.loads(m.group(0))
    return {'tool': str(data.get('tool') or ''),
            'args': data.get('args') if isinstance(data.get('args'), dict) else {}}


# --- 演示商品规则兜底（与线上分类键一致：books/electronics/living/sports）--------
_DEMO_TEMPLATES = {
    'books': ('配套教材', '课后习题册', '课堂笔记', '复习提纲'),
    'electronics': ('充电器', '耳机', '桌面支架', '数据线'),
    'living': ('收纳盒', '台灯', '水杯', '置物架'),
    'sports': ('跳绳', '瑜伽垫', '羽毛球拍', '护腕'),
}
_DEMO_CONDITIONS = ('近乎全新', '正常使用痕迹', '明显磨损，已说明')


def _rule_demo_items(prompt, count):
    """模型不可用时的确定性预览：可复现、不写库。"""
    prompt = str(prompt or '').strip()[:16] or '校园好物'
    cats = ['books'] if any(k in prompt for k in ('书', '教材', '笔记', '习题')) else \
           ['electronics'] if any(k in prompt for k in ('电子', '充电', '耳机', '电脑', '手机', '键盘')) else \
           ['sports'] if any(k in prompt for k in ('运动', '健身', '球', '瑜伽', '跳绳', '跑步')) else \
           ['living'] if any(k in prompt for k in ('宿舍', '收纳', '台灯', '水杯', '置物', '寝室')) else \
           ['books', 'electronics', 'living', 'sports']
    items = []
    for i in range(count):
        category = cats[i % len(cats)]
        suffix = _DEMO_TEMPLATES[category][(i // len(cats)) % 4]
        # 价格按「序号回绕」展开，始终落在 0—2000 元的入库校验区间内。
        items.append({'title': ('%s·%s' % (prompt, suffix))[:40], 'category': category,
                      'price': (900 + (i % 4) * 300) * 100,
                      'condition': _DEMO_CONDITIONS[i % 3],
                      'description': '%s主题的演示商品，校园内公共区域面交，具体成色以实物为准。' % prompt})
    return items


def _demo_item_rows(items):
    return [{'title': it['title'], 'meta': '¥%.2f · %s' % (it['price'] / 100, it['condition'])}
            for it in items]


class WorkMode:
    """owner 工作模式（D1 版）。混入 Api；所有入口都重新校验 owner 身份。"""

    JOB_TTL = 600

    async def work_owner(self, request):
        """所有工具都重新鉴权；前端显示与模型输出不能授予 L1。"""
        uid, role = await self.cf_staff_actor(request)
        require(role == 'owner', '仅平台所有者可使用工作模式', 403)
        return uid

    # ---- HTTP 入口 ---------------------------------------------------------

    async def work_tools(self, request):
        await self.work_owner(request)
        return json_response({'tools': catalog()})

    async def work_chat(self, request):
        uid = await self.work_owner(request)
        d = await json_body(request)
        question = ValidationMixin.text(d.get('question'), 500, '问题')
        return json_response(await self._work_agent(uid, question))

    async def work_call(self, request):
        uid = await self.work_owner(request)
        d = await json_body(request)
        name = str(d.get('tool') or '')
        require(name in TOOLS, '未知工具', 404)
        args = d.get('args') if isinstance(d.get('args'), dict) else {}
        token = str(d.get('token') or '')
        if TOOLS[name]['risk'] != 'read' and not token:
            return json_response(await self._work_propose(uid, name, args))
        if token:
            return json_response(await self._work_run_job(uid, token, expect=name))
        return json_response(await self._work_read(uid, name, args))

    async def work_confirm(self, request):
        uid = await self.work_owner(request)
        d = await json_body(request)
        token = str(d.get('token') or '')
        require(token, '缺少确认令牌', 400)
        return json_response(await self._work_run_job(uid, token))

    # ---- ReAct 循环 --------------------------------------------------------

    async def _work_quota(self, uid):
        """工作模式的每日额度：只设上限，不设「问得太快」间隔。

        多步循环里一秒内会连调几次规划器，套用客服聊天的 2 秒间隔会把
        第二步直接判 429；所有者是受信操作员，按天封顶就够。
        """
        s = await self.ai_settings()
        limit = int(s['staff_daily_limit'] or 100)
        day = time.strftime('%Y-%m-%d', time.gmtime(time.time() + 8 * 3600))
        row = await self.db.first('SELECT count FROM ai_usage WHERE user_id=? AND day=?', (uid, day))
        require(int((row or {}).get('count') or 0) < limit, '今天的 AI 提问次数已用完，请明天再用或调高额度', 429)

    async def _work_agent(self, uid, question):
        q = question.strip()
        # 1. 账号动作先认出来：直接出 proposal，不调模型（防提示词注入改人）。
        act = account_action(q)
        if act:
            target = await self._work_target(act['name'])
            if not target:
                return {'answer': '没找到「%s」对应的运营账号。请说完整昵称，或到管理台操作。' % act['name'],
                        'items': [], 'proposal': None, 'mode': 'rule'}
            if target['role'] == 'owner':
                return {'answer': '所有者账号不能通过助手调整，只能由运维在数据库处理。',
                        'items': [], 'proposal': None, 'mode': 'rule'}
            tool = {'role': 'user_role', 'ban': 'user_ban',
                    'disable': 'user_disable', 'revoke': 'user_revoke'}[act['kind']]
            args = {'target': target['id'], 'nickname': target['nickname']}
            if tool == 'user_role':
                args['role'] = act['role']
            if tool == 'user_ban':
                args.update({'banned': True, 'reason': '工作模式封禁'})
            return await self._work_propose(uid, tool, args)

        # 2. ReAct 多步循环：规划 → 执行读工具 → 观察回填 → 再规划；写工具即转确认卡。
        observations = []
        demo_items = None
        last = None
        await self._work_quota(uid)
        for _ in range(3):
            try:
                plan = await work_plan(q, catalog(), observations, self.env)
            except Exception:  # noqa: BLE001 - 规划失败不阻断工作模式，退回规则路由
                break
            await self.ai_count(uid)
            tool = plan['tool']
            if tool in ('', 'final'):
                return last if last else await self._work_rule(uid, q)
            if tool not in TOOLS:
                break
            args = plan['args']
            # 「生成预览 → 确认入库」的衔接：预览项由后端传递，不经模型转抄。
            if tool == 'demo_publish' and not args.get('items') and demo_items:
                args = dict(args, items=demo_items)
            if tool == 'demo_publish' and not args.get('items'):
                return {'answer': '还没有可入库的预览项。请说「发布 3 件宿舍好物演示商品」，我先出预览再给确认卡。',
                        'items': [], 'proposal': None, 'mode': 'rule'}
            if TOOLS[tool]['risk'] == 'read':
                result = await self._work_read(uid, tool, args)
                if tool == 'demo_generate':
                    demo_items = (result.get('data') or {}).get('items')
                last = result
                observations.append({'tool': tool, 'args': args,
                                     'answer': str(result.get('answer') or '')[:300],
                                     'items': [str(i.get('title')) for i in (result.get('items') or [])][:8]})
            else:
                return await self._work_propose(uid, tool, args)
        return last if last else await self._work_rule(uid, q)

    async def _work_target(self, name):
        name = str(name or '').strip().strip('「」"“”')
        if not name:
            return None
        rows = await self.db.all("SELECT id,nickname,role,status FROM users WHERE nickname LIKE ? AND status='active'",
                                 ('%' + name + '%',))
        if not rows:
            return None
        rows.sort(key=lambda r: ROLE_RANK.get(r['role'], -1), reverse=True)
        return rows[0]

    async def _work_rule(self, uid, q):
        """模型不可用时的关键词规则路由（与本地同序）。"""
        def keyword():
            m = re.search(r'(?:查|找|搜索|看看)\s*[「"“]?([^」"”\s，。]{1,20})', q)
            word = m.group(1) if m else ''
            return '' if word in ('用户', '账号', '成员', '商品', '订单', '工单', '审计') else word

        # 演示商品 + 发布/入库：先出预览，再直接给确认卡（预览项显示在卡里）。
        if '演示' in q and any(w in q for w in ('发布', '入库', '上架')):
            hit = re.search(r'(\d+)\s*件', q)
            count = max(1, min(int(hit.group(1)), 10)) if hit else 5
            preview = await self._work_read(uid, 'demo_generate',
                                            {'prompt': keyword() or '校园好物', 'count': count})
            return await self._work_propose(uid, 'demo_publish',
                                            {'items': (preview.get('data') or {}).get('items') or []})

        rules = (
            (('演示商品',), 'demo_generate', {'prompt': keyword() or '校园好物', 'count': 5}),
            (('用户', '账号', '成员', '谁'), 'users', {'q': keyword()}),
            (('商品', '在售', '下架'), 'products', {'q': keyword()}),
            (('订单', '成交', '退款'), 'orders', {'days': 7}),
            (('工单', '待处理', '处理中', '复核'), 'tickets', {'status': 'open' if '待处理' in q else ''}),
            (('审计', '操作记录'), 'audit', {'days': 7}),
            (('趋势', '统计'), 'stats', {'days': 7}),
            (('会话', '聊天'), 'rooms', {}),
            (('举报', '治理', '审核'), 'moderation', {}),
            (('信誉', '低分'), 'credit', {}),
            (('议价', '出价', '还价'), 'offers', {}),
            (('帖子', '社区', '评论'), 'posts', {'q': keyword()}),
            (('账本', '流水', '资金'), 'ledger', {}),
            (('排行', '卖家'), 'sellers', {'days': 7}),
        )
        for words, tool, args in rules:
            if any(w in q for w in words):
                return await self._work_read(uid, tool, {k: v for k, v in args.items() if v not in ('', None)})
        return await self._work_read(uid, 'overview', {})

    # ---- 读工具：确定性 SQL，不经过模型 --------------------------------------

    async def _work_read(self, uid, name, args):
        out = await getattr(self, '_read_' + name)(uid, args)
        out.setdefault('tool', name)
        out.setdefault('mode', 'rule')
        return out

    async def _read_overview(self, uid, a):
        now = time.time(); since = now - 86400
        u = await self.db.first("SELECT COUNT(*) total,SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active FROM users")
        s = await self.db.first('SELECT COUNT(DISTINCT user_id) n FROM sessions WHERE expires>?', (now,))
        p = await self.db.first("SELECT COUNT(*) n FROM products WHERE status='available'")
        o = await self.db.first('SELECT COUNT(*) n FROM orders WHERE created>=?', (since,))
        t = await self.db.first("SELECT SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) open,"
                                "SUM(CASE WHEN status IN ('processing','review') THEN 1 ELSE 0 END) busy FROM tickets")
        stats = {'users': int((u or {}).get('total') or 0), 'active_24h': int((s or {}).get('n') or 0),
                 'products': int((p or {}).get('n') or 0), 'orders_24h': int((o or {}).get('n') or 0),
                 'tickets_open': int((t or {}).get('open') or 0), 'tickets_processing': int((t or {}).get('busy') or 0)}
        answer = ('平台概览：活跃用户 {users}（24h {active_24h}），在售商品 {products}，'
                  '24h 订单 {orders_24h}，待处理工单 {tickets_open}，处理中 {tickets_processing}。').format(**stats)
        return {'answer': answer, 'items': [{'title': k, 'meta': str(v)} for k, v in stats.items()], 'data': stats}

    async def _read_users(self, uid, a):
        sql = "SELECT id,nickname,role,status,phone,college,score FROM users WHERE status<>'deleted'"
        params = []
        q = str(a.get('q') or '').strip()
        if q:
            sql += ' AND (nickname LIKE ? OR phone LIKE ?)'
            params += ['%' + q + '%', '%' + q + '%']
        if a.get('role'):
            sql += ' AND role=?'
            params.append(a['role'])
        if a.get('status'):
            sql += ' AND status=?'
            params.append(a['status'])
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 20))
        rows = await self.db.all(sql, tuple(params))
        items = [{'title': r['nickname'], 'meta': '%s · %s · %s · %s分' % (
            ROLE_LABELS.get(r['role'], r['role']), r['status'], _mask(r['phone']), r['score'])} for r in rows]
        return {'answer': '找到 %d 个账号（手机号已打码，需要全号请查用户详情）。' % len(rows), 'items': items,
                'data': [dict(r, phone=_mask(r['phone'])) for r in rows]}

    async def _read_user_detail(self, uid, a):
        target = _int(a.get('id'))
        r = await self.db.first('SELECT id,nickname,role,status,phone,college,major,score,last_login FROM users WHERE id=?', (target,))
        require(r, '用户不存在', 404)
        reveal = bool(a.get('reveal'))
        if reveal:
            await self.db.run('INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) '
                              'VALUES(?,?,?,?,?,?,?)', (uid, target, 'pii_view', None, '工作模式查看完整手机号', None, time.time()))
        data = dict(r)
        data['phone'] = r['phone'] if reveal else _mask(r['phone'])
        data['products'] = int((await self.db.first('SELECT COUNT(*) n FROM products WHERE seller_id=?', (target,)))['n'])
        data['orders'] = int((await self.db.first('SELECT COUNT(*) n FROM orders WHERE buyer_id=? OR seller_id=?', (target, target)))['n'])
        data['tickets'] = int((await self.db.first('SELECT COUNT(*) n FROM tickets WHERE user_id=?', (target,)))['n'])
        recent = await self.db.all('SELECT id,title,price,status FROM products WHERE seller_id=? ORDER BY id DESC LIMIT 5', (target,))
        items = [{'title': '#%s %s' % (p['id'], p['title']), 'meta': '%s · ¥%.2f' % (
            PRODUCT_STATUS.get(p['status'], p['status']), p['price'] / 100)} for p in recent]
        return {'answer': '用户「%s」：%s，%s，%s分；商品 %d，订单 %d，工单 %d。' % (
            r['nickname'], ROLE_LABELS.get(r['role'], r['role']), r['status'], r['score'],
            data['products'], data['orders'], data['tickets']), 'items': items, 'data': data}

    async def _read_products(self, uid, a):
        sql = ('SELECT p.id,p.title,p.category,p.price,p.status,p.seller_id,p.created,u.nickname '
               'FROM products p JOIN users u ON u.id=p.seller_id WHERE 1=1')
        params = []
        if a.get('q'):
            sql += ' AND p.title LIKE ?'
            params.append('%' + str(a['q']) + '%')
        if a.get('category'):
            sql += ' AND p.category=?'
            params.append(a['category'])
        if a.get('status'):
            sql += ' AND p.status=?'
            params.append(a['status'])
        if a.get('seller'):
            sql += ' AND p.seller_id=?'
            params.append(_int(a.get('seller')))
        sql += ' ORDER BY p.id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 20))
        rows = await self.db.all(sql, tuple(params))
        items = [{'title': '#%s %s' % (r['id'], r['title']), 'meta': '%s · %s · ¥%.2f · %s' % (
            r['category'], r['nickname'], r['price'] / 100, PRODUCT_STATUS.get(r['status'], r['status']))} for r in rows]
        return {'answer': '找到 %d 件商品。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_product_detail(self, uid, a):
        pid = _int(a.get('id'))
        r = await self.db.first('SELECT p.*,u.nickname FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?', (pid,))
        require(r, '商品不存在', 404)
        data = dict(r)
        data.pop('data', None)
        # 不用 json_each：本地内存 SQLite 未必编了 JSON1，扫最近订单在 Python 侧匹配。
        orders = []
        for o in await self.db.all('SELECT id,status,total,items FROM orders ORDER BY id DESC LIMIT 100'):
            try:
                items = json.loads(o['items'] or '[]')
            except ValueError:
                continue
            if any(_int(p.get('id')) == pid for p in items):
                orders.append(o)
            if len(orders) >= 5:
                break
        return {'answer': '商品「%s」：%s，%s，¥%.2f，卖家 %s。' % (
            r['title'], r['category'], PRODUCT_STATUS.get(r['status'], r['status']),
            r['price'] / 100, r['nickname']),
            'items': [{'title': '订单 #%s' % o['id'], 'meta': '%s · ¥%.2f' % (
                ORDER_STATUS.get(o['status'], o['status']), o['total'] / 100)} for o in orders],
            'data': data}

    async def _read_orders(self, uid, a):
        sql = ('SELECT o.id,o.buyer_id,o.seller_id,o.status,o.total,o.created,b.nickname buyer,s.nickname seller '
               'FROM orders o JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE 1=1')
        params = []
        if a.get('status'):
            sql += ' AND o.status=?'
            params.append(a['status'])
        if a.get('buyer'):
            sql += ' AND o.buyer_id=?'
            params.append(_int(a.get('buyer')))
        if a.get('seller'):
            sql += ' AND o.seller_id=?'
            params.append(_int(a.get('seller')))
        if a.get('days'):
            sql += ' AND o.created>=?'
            params.append(time.time() - _int(a.get('days'), 7) * 86400)
        sql += ' ORDER BY o.id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 20))
        rows = await self.db.all(sql, tuple(params))
        items = [{'title': '订单 #%s' % r['id'], 'meta': '%s · %s → %s · ¥%.2f' % (
            ORDER_STATUS.get(r['status'], r['status']), r['buyer'], r['seller'], r['total'] / 100)} for r in rows]
        return {'answer': '找到 %d 笔订单。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_order_detail(self, uid, a):
        oid = _int(a.get('id'))
        r = await self.db.first('SELECT o.*,b.nickname buyer,s.nickname seller FROM orders o '
                                'JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE o.id=?', (oid,))
        require(r, '订单不存在', 404)
        data = dict(r)
        try:
            data['items'] = json.loads(r['items'] or '[]')
        except ValueError:
            data['items'] = []
        return {'answer': '订单 #%s：%s，%s → %s，¥%.2f。' % (
            oid, ORDER_STATUS.get(r['status'], r['status']), r['buyer'], r['seller'], r['total'] / 100),
            'items': [{'title': p.get('title') or '商品', 'meta': '¥%.2f' % (_int(p.get('price')) / 100)}
                      for p in data['items']], 'data': data}

    async def _read_tickets(self, uid, a):
        sql = ('SELECT t.id,t.type,t.subject,t.status,t.user_id,t.created,u.nickname '
               'FROM tickets t JOIN users u ON u.id=t.user_id WHERE 1=1')
        params = []
        if a.get('status'):
            sql += ' AND t.status=?'
            params.append(a['status'])
        if a.get('type'):
            sql += ' AND t.type=?'
            params.append(a['type'])
        if a.get('q'):
            sql += ' AND (t.subject LIKE ? OR t.body LIKE ?)'
            params += ['%' + str(a['q']) + '%', '%' + str(a['q']) + '%']
        sql += ' ORDER BY t.id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 20))
        rows = await self.db.all(sql, tuple(params))
        items = [{'title': '#%s %s' % (r['id'], r['subject']), 'meta': '%s · %s · %s · %s' % (
            r['type'], TICKET_STATUS.get(r['status'], r['status']), r['nickname'],
            time.strftime('%m-%d %H:%M', time.localtime(r['created'])))} for r in rows]
        return {'answer': '找到 %d 张工单。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_ticket_detail(self, uid, a):
        tid = _int(a.get('id'))
        r = await self.db.first('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?', (tid,))
        require(r, '工单不存在', 404)
        msgs = await self.db.all('SELECT m.id,m.user_id,m.body,m.internal,m.created,u.nickname FROM ticket_messages m '
                                 'JOIN users u ON u.id=m.user_id WHERE m.ticket_id=? ORDER BY m.id', (tid,))
        data = dict(r)
        data['messages'] = [dict(x) for x in msgs]
        return {'answer': '工单 #%s「%s」：%s，%s 提交，共 %d 条消息。' % (
            tid, r['subject'], TICKET_STATUS.get(r['status'], r['status']), r['nickname'], len(msgs)),
            'items': [{'title': ('内部' if x['internal'] else '公开') + ' · ' + x['nickname'],
                       'meta': str(x['body'])[:60]} for x in msgs], 'data': data}

    async def _read_audit(self, uid, a):
        sql = 'SELECT id,actor,target,type,delta,reason,ticket_id,created FROM audit WHERE 1=1'
        params = []
        if a.get('actor'):
            sql += ' AND actor=?'
            params.append(_int(a.get('actor')))
        if a.get('type'):
            sql += ' AND type=?'
            params.append(a['type'])
        if a.get('days'):
            sql += ' AND created>=?'
            params.append(time.time() - _int(a.get('days'), 7) * 86400)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 50, 100))
        rows = await self.db.all(sql, tuple(params))
        items = [{'title': '#%s %s' % (r['id'], r['type']), 'meta': '%s · actor %s · target %s' % (
            str(r['reason'] or '')[:40], r['actor'], r['target'])} for r in rows]
        return {'answer': '最近 %d 条审计记录。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_stats(self, uid, a):
        days = max(1, min(_int(a.get('days'), 7), 30))
        since = time.time() - days * 86400

        def by_day(rows):
            out = {}
            for r in rows:
                key = time.strftime('%m-%d', time.localtime(r['created']))
                out[key] = out.get(key, 0) + 1
            return out

        users_total = int((await self.db.first("SELECT COUNT(*) n FROM users WHERE status='active'"))['n'])
        orders = by_day(await self.db.all('SELECT created FROM orders WHERE created>=?', (since,)))
        tickets = by_day(await self.db.all('SELECT created FROM tickets WHERE created>=?', (since,)))
        items = [{'title': d, 'meta': '订单 %s · 工单 %s' % (orders.get(d, 0), tickets.get(d, 0))}
                 for d in sorted(set(orders) | set(tickets))]
        return {'answer': '最近 %d 天新增：订单 %d，工单 %d；当前活跃用户 %d。' % (
            days, sum(orders.values()), sum(tickets.values()), users_total), 'items': items,
            'data': {'users_total': users_total, 'orders': orders, 'tickets': tickets}}

    async def _read_rooms(self, uid, a):
        sql = ("SELECT r.id,r.kind,r.name,r.support,r.assignee,r.ticket_id,r.support_status,r.college,"
               "(SELECT MAX(created) FROM messages x WHERE x.room_id=r.id) last_at FROM rooms r WHERE 1=1")
        params = []
        if a.get('kind'):
            sql += ' AND r.kind=?'
            params.append(a['kind'])
        if str(a.get('support')).lower() in ('1', 'true'):
            sql += ' AND r.support=1'
        sql += ' ORDER BY COALESCE(last_at,0) DESC, r.id DESC LIMIT ?'
        params.append(_limit(a.get('limit'), 20))
        rows = await self.db.all(sql, tuple(params))
        items = []
        for r in rows:
            who = '客服' if r['support'] else ('受理人 #%s' % r['assignee'] if r['assignee'] else '未分配')
            last = time.strftime('%m-%d %H:%M', time.localtime(r['last_at'])) if r['last_at'] else '无消息'
            items.append({'title': r['name'] or ('会话 #%s' % r['id']),
                          'meta': '%s · %s%s · 最近 %s' % (r['kind'], who,
                                                         (' · ' + r['support_status']) if r['support'] else '', last)})
        return {'answer': '找到 %d 个会话。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_messages(self, uid, a):
        rid = _int(a.get('room'))
        room = await self.db.first('SELECT id,name,kind,support FROM rooms WHERE id=?', (rid,))
        require(room, '会话不存在', 404)
        await self.db.run('INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) '
                          'VALUES(?,?,?,?,?,?,?)', (uid, rid, 'chat_view', None, '工作模式查看聊天记录', None, time.time()))
        rows = list(reversed(await self.db.all(
            "SELECT m.id,m.user_id,m.removed,CASE WHEN m.removed=1 THEN '消息已被移除' WHEN m.removed=2 THEN '' ELSE m.body END body,"
            'm.created,usr.nickname FROM messages m JOIN users usr ON usr.id=m.user_id '
            'WHERE m.room_id=? AND m.removed<>3 ORDER BY m.id DESC LIMIT ?',
            (rid, _limit(a.get('limit'), 20)))))
        items = [{'title': r['nickname'], 'meta': str(r['body'])[:80]} for r in rows]
        return {'answer': '会话「%s」最近 %d 条消息（已记录查看审计）。' % (
            room['name'] or ('#%s' % rid), len(rows)), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_moderation(self, uid, a):
        lim = _limit(a.get('limit'), 10)
        reports = await self.db.all("SELECT id,subject,status,created FROM tickets WHERE type='report' "
                                    "AND status IN ('open','processing','review') ORDER BY id DESC LIMIT ?", (lim,))
        posts = await self.db.all('SELECT id,substr(body,1,60) body,created FROM posts WHERE removed=1 ORDER BY id DESC LIMIT 5')
        messages = await self.db.all("SELECT id,room_id,substr(body,1,60) body,created FROM messages WHERE removed IN (1,2) ORDER BY id DESC LIMIT 5")
        items = [{'title': '#%s %s' % (r['id'], r['subject']), 'meta': '举报 · ' + r['status']} for r in reports]
        items += [{'title': '帖子 #%s' % r['id'], 'meta': str(r['body'])[:50]} for r in posts]
        items += [{'title': '消息 #%s' % r['id'], 'meta': '会话 #%s · %s' % (r['room_id'], str(r['body'])[:40])} for r in messages]
        return {'answer': '待处理举报 %d 条，已移除帖子 %d 条、消息 %d 条。' % (len(reports), len(posts), len(messages)),
                'items': items,
                'data': {'reports': [dict(r) for r in reports], 'posts': [dict(r) for r in posts],
                         'messages': [dict(r) for r in messages]}}

    async def _read_credit(self, uid, a):
        threshold = max(0, min(_int(a.get('threshold'), 80), 100))
        low = await self.db.all("SELECT id,nickname,score,status FROM users WHERE score<=? AND status='active' "
                                "ORDER BY score,id LIMIT ?", (threshold, _limit(a.get('limit'), 20)))
        recent = await self.db.all("SELECT id,actor,target,delta,reason,created FROM audit WHERE type='credit' "
                                   "ORDER BY id DESC LIMIT 8")
        items = [{'title': r['nickname'], 'meta': '%s 分 · #%s' % (r['score'], r['id'])} for r in low]
        items += [{'title': '信誉变动 #%s' % r['id'], 'meta': '%+d · %s' % (r['delta'] or 0, str(r['reason'])[:30])}
                  for r in recent]
        return {'answer': '信誉 ≤ %d 的活跃账号 %d 个；最近信誉变动 %d 条。' % (threshold, len(low), len(recent)),
                'items': items, 'data': {'low': [dict(r) for r in low], 'recent': [dict(r) for r in recent]}}

    async def _read_offers(self, uid, a):
        rows = await self.db.all('SELECT o.id,o.product_id,o.buyer_id,o.amount,o.status,o.created,p.title,u.nickname '
                                 'FROM offers o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id '
                                 'ORDER BY o.id DESC LIMIT ?', (_limit(a.get('limit'), 20),))
        items = [{'title': '#%s %s' % (r['id'], r['title']), 'meta': '%s · ¥%.2f · %s' % (
            r['nickname'], r['amount'] / 100, r['status'])} for r in rows]
        return {'answer': '最近 %d 条出价记录。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}

    async def _read_posts(self, uid, a):
        q = str(a.get('q') or '').strip()
        lim = _limit(a.get('limit'), 20)
        if q:
            posts = await self.db.all('SELECT id,user_id,substr(body,1,80) body,removed,created FROM posts '
                                      'WHERE body LIKE ? ORDER BY id DESC LIMIT ?', ('%' + q + '%', lim))
            comments = await self.db.all('SELECT id,post_id,substr(body,1,80) body,created FROM comments '
                                         'WHERE body LIKE ? ORDER BY id DESC LIMIT ?', ('%' + q + '%', lim))
        else:
            posts = await self.db.all('SELECT id,user_id,substr(body,1,80) body,removed,created FROM posts ORDER BY id DESC LIMIT ?', (lim,))
            comments = await self.db.all('SELECT id,post_id,substr(body,1,80) body,created FROM comments ORDER BY id DESC LIMIT ?', (lim,))
        items = [{'title': '帖子 #%s' % r['id'], 'meta': ('已移除 · ' if r['removed'] else '') + str(r['body'])[:50]} for r in posts]
        items += [{'title': '评论 #%s' % r['id'], 'meta': '帖子 #%s · %s' % (r['post_id'], str(r['body'])[:40])} for r in comments]
        return {'answer': '找到帖子 %d 条、评论 %d 条。' % (len(posts), len(comments)), 'items': items,
                'data': {'posts': [dict(r) for r in posts], 'comments': [dict(r) for r in comments]}}

    async def _read_ledger(self, uid, a):
        sums = await self.db.all('SELECT kind,SUM(amount) total,COUNT(*) n FROM ledger GROUP BY kind ORDER BY kind')
        recent = await self.db.all('SELECT id,order_id,kind,amount,created FROM ledger ORDER BY id DESC LIMIT 10')
        items = [{'title': r['kind'], 'meta': '%d 笔 · ¥%.2f' % (r['n'], (r['total'] or 0) / 100)} for r in sums]
        items += [{'title': '流水 #%s' % r['id'], 'meta': '%s · ¥%.2f · 订单 #%s' % (
            r['kind'], r['amount'] / 100, r['order_id'])} for r in recent]
        return {'answer': '账本共 %d 种类型；最近 %d 条流水。' % (len(sums), len(recent)), 'items': items,
                'data': {'sums': [dict(r) for r in sums], 'recent': [dict(r) for r in recent]}}

    async def _read_sellers(self, uid, a):
        days = max(1, min(_int(a.get('days'), 7), 90))
        since = time.time() - days * 86400
        rows = await self.db.all("SELECT o.seller_id,COUNT(*) n,SUM(o.total) gmv,u.nickname FROM orders o "
                                 "JOIN users u ON u.id=o.seller_id WHERE o.status='completed' AND o.created>=? "
                                 "GROUP BY o.seller_id ORDER BY gmv DESC LIMIT ?", (since, _limit(a.get('limit'), 10, 20)))
        items = [{'title': r['nickname'], 'meta': '%d 单 · ¥%.2f' % (r['n'], (r['gmv'] or 0) / 100)} for r in rows]
        return {'answer': '最近 %d 天成交卖家 %d 位。' % (days, len(rows)), 'items': items,
                'data': [dict(r) for r in rows]}

    async def _read_demo_generate(self, uid, a):
        """生成演示商品预览：只返回，不入库；模型不可用走规则兜底。"""
        prompt = str(a.get('prompt') or '').strip()[:16] or '校园好物'
        count = max(1, min(_int(a.get('count'), 5), 10))
        await self._work_quota(uid)
        items = []
        mode = 'rule'
        try:
            raw = await call_llm(PRODUCT_SYSTEM, '主题：%s\n数量：%d 件' % (prompt, count),
                                 self.env, max_tokens=1200, model=getattr(self.env, 'HC_AI_MODEL_OWNER', '') or None)
            items = parse_products_json(raw)
            if items:
                mode = 'llm'
        except Exception:  # noqa: BLE001 - 生成失败不写库，走规则兜底
            items = []
        if not items:
            items = _rule_demo_items(prompt, count)
        for idx, item in enumerate(items):
            item['photo'] = demo_photo_for(item['category'], idx)
        if mode == 'llm':
            await self.ai_count(uid)
        return {'answer': '已生成 %d 件「%s」演示商品预览（尚未入库）。说「确认入库」或点确认后才会写入。' % (len(items), prompt),
                'items': _demo_item_rows(items), 'data': {'items': items, 'prompt': prompt}, 'mode': mode}

    # ---- 写工具：proposal + ai_office_jobs 一次性作业 ------------------------

    async def _work_validate(self, uid, name, args):
        """出 proposal 前就校验目标，避免给 owner 一张执行必失败的确认卡。"""
        if name in ('user_role', 'user_disable', 'user_revoke', 'user_ban', 'user_credit'):
            target = _int(args.get('target'))
            t = await self.db.first('SELECT id,nickname,role,status FROM users WHERE id=?', (target,))
            require(t, '账号不存在', 404)
            require(t['role'] != 'owner', '所有者账号不能被工作模式调整', 403)
            require(target != uid, '不能对自己执行此操作', 403)
        if name == 'user_role':
            require(args.get('role') in ('user', 'support', 'admin', 'developer'), '目标角色无效')
        if name == 'product_moderate':
            require(await self.db.first('SELECT id FROM products WHERE id=?', (_int(args.get('id')),)), '商品不存在', 404)
            require(args.get('action') in ('delist', 'restore'), '处置动作必须是 delist 或 restore')
        if name == 'product_promote':
            require(await self.db.first('SELECT id FROM products WHERE id=?', (_int(args.get('id')),)), '商品不存在', 404)
            require(args.get('tier') in ('1d', '3d', '7d'), '置顶档位必须是 1d/3d/7d')
        if name == 'product_batch_delist':
            seller = _int(args.get('seller'))
            require(await self.db.first('SELECT id FROM users WHERE id=?', (seller,)), '卖家不存在', 404)
            require(await self.db.scalar("SELECT COUNT(*) FROM products WHERE seller_id=? AND status='available'", (seller,)),
                    '该卖家当前没有在售商品可下架')
        if name == 'product_bulk_moderate':
            require(args.get('action') in ('delist', 'restore'), '批量动作必须是 delist 或 restore')
            require(any(args.get(k) for k in ('q', 'category', 'seller')), '批量处置至少要给一个筛选条件（关键词/分类/卖家）')
            require(await self._work_bulk_count(args), '没有符合条件的商品')
        if name == 'content_remove':
            require(args.get('kind') in ('post', 'message'), '内容类型必须是 post 或 message')
            table = 'posts' if args.get('kind') == 'post' else 'messages'
            require(await self.db.first('SELECT id FROM %s WHERE id=?' % table, (_int(args.get('id')),)), '内容不存在', 404)
        if name in ('ticket_reply', 'ticket_resolve'):
            require(await self.db.first('SELECT id FROM tickets WHERE id=?', (_int(args.get('id')),)), '工单不存在', 404)
        if name == 'notification_send':
            require(await self.db.first('SELECT id FROM users WHERE id=?', (_int(args.get('target')),)), '收件账号不存在', 404)
        if name == 'user_credit':
            delta = args.get('delta')
            require(type(delta) is int and delta != 0 and -100 <= delta <= 100, '信誉变动必须是 -100 到 100 之间且不能为 0')
            t = await self.db.first('SELECT id,status FROM tickets WHERE id=?', (_int(args.get('ticket')),))
            require(t, '关联工单不存在', 404)
            require(t['status'] == 'resolved', '只能基于已结案工单调整信誉')
        if name == 'ai_settings':
            for key in ('daily_limit', 'staff_daily_limit'):
                if args.get(key) is not None:
                    value = args.get(key)
                    require(type(value) is int and 1 <= value <= 500, '额度必须是 1—500 的整数')
        if name == 'demo_publish':
            require(clean_product_items(args.get('items')), '商品数据不合法')

    async def _work_bulk_count(self, args):
        """批量处置的命中数量（上限 50），proposal 与 execute 共用同一筛选。"""
        action = args.get('action')
        sql = 'SELECT COUNT(*) n FROM products WHERE status=?'
        params = ['available' if action == 'delist' else 'removed']
        if args.get('q'):
            sql += ' AND title LIKE ?'
            params.append('%' + str(args['q']) + '%')
        if args.get('category'):
            sql += ' AND category=?'
            params.append(args['category'])
        if args.get('seller'):
            sql += ' AND seller_id=?'
            params.append(_int(args.get('seller')))
        sql += ' LIMIT 50'
        return int((await self.db.first(sql, tuple(params)))['n'])

    async def _work_propose(self, uid, name, args):
        """写工具只落一条待确认作业；10 分钟过期；重复发起会覆盖旧作业。"""
        spec = TOOLS[name]
        await self._work_validate(uid, name, args)
        summary = _summary(name, args)
        if name == 'product_bulk_moderate':
            summary = '%s（命中 %d 件）' % (summary, await self._work_bulk_count(args))
        now = time.time()
        job = secrets.token_hex(16)
        payload = json.dumps({'tool': name, 'args': args}, ensure_ascii=False)
        await self.require_capacity()
        await self.db.guarded_batch(
            "SELECT 1 FROM users WHERE id=? AND role='owner' AND status='active'", (uid,),
            [('INSERT INTO ai_office_jobs(id,actor,payload,state,created,expires) VALUES(?,?,?,?,?,?)',
              (job, uid, payload, 'pending', now, now + self.JOB_TTL))])
        return {'answer': '这是不可逆操作，请再次确认：%s。' % summary,
                'proposal': {'tool': name, 'title': spec['title'], 'summary': summary,
                             'risk': spec['risk'], 'args': args},
                'token': job, 'tool': name, 'mode': 'rule'}

    async def _work_run_job(self, uid, token, expect=None):
        """执行已确认的作业：同 batch 内复查身份/状态/参数，业务写入与作业完成一起提交。"""
        job = await self.db.first('SELECT * FROM ai_office_jobs WHERE id=?', (token,))
        require(job, '待执行计划不存在，请重新发起', 404)
        require(job['actor'] == uid, '不能执行其他所有者的计划', 403)
        if job['state'] == 'completed':
            # 幂等：双击确认 / 网络重试拿到同一份回执，不再改一次数据。
            done = json.loads(job.get('result') or '{}')
            return {'ok': True, 'tool': done.get('tool') or '', 'result': done.get('result') or {},
                    'repeat': True}
        require(job['state'] == 'pending' and job['expires'] > time.time(), '计划已过期，请重新发起', 409)
        payload = json.loads(job['payload'])
        name = payload['tool']
        if expect:
            require(name == expect, '确认令牌与所调工具不一致', 403)
        result = await self._work_execute(uid, name, payload['args'], token)
        return {'ok': True, 'tool': name, 'result': result}

    # ---- 写工具执行：全部走 guarded_batch，要么全成要么全不成 ----------------

    async def _work_execute(self, uid, name, args, job=None):
        """执行写工具；带 job 时把「作业完成」并入同一批次，保证不重复执行。"""
        await self._work_validate(uid, name, args)
        guard, guard_args, statements = await self._work_plan_statements(uid, name, args)
        result = await self._work_result(name, args)
        if job:
            # 作业复查作为子查询挂在守卫的 WHERE 后面：cf_staff_commit 会把守卫
            # 整个套进 EXISTS(...)，两个 SELECT 用 AND 连不是合法语句。
            guard = guard + (" AND EXISTS(SELECT 1 FROM ai_office_jobs WHERE id=? AND actor=? "
                             "AND state='pending' AND payload=? AND expires>?)")
            guard_args = tuple(guard_args) + (
                job, uid, json.dumps({'tool': name, 'args': args}, ensure_ascii=False), time.time())
            statements.append(("UPDATE ai_office_jobs SET state='completed',result=? WHERE id=?",
                               (json.dumps({'ok': True, 'tool': name, 'result': result},
                                           ensure_ascii=False), job)))
        await self.cf_staff_commit(uid, guard, guard_args, statements, ('owner',))
        return result

    async def _work_result(self, name, args):
        if name == 'demo_publish':
            return {'ok': True, 'count': len(args.get('items') or [])}
        return {'ok': True}

    async def _work_plan_statements(self, uid, name, args):
        """返回 (guard_sql, guard_args, statements)；调用方负责提交。"""
        now = time.time()
        audit = lambda kind, reason, target=None, tid=None, delta=None: self.cf_staff_audit(uid, kind, reason, target, tid, delta)
        if name == 'user_role':
            target = _int(args.get('target'))
            t = await self.db.first('SELECT id,role FROM users WHERE id=?', (target,))
            return ('SELECT 1 FROM users WHERE id=? AND role=? AND status=\'active\'', (target, t['role']),
                    [("UPDATE users SET role=? WHERE id=?", (args['role'], target)),
                     ('DELETE FROM sessions WHERE user_id=?', (target,)),
                     audit('ai_work_role', '工作模式调整角色为 %s' % args['role'], target)])
        if name == 'user_disable':
            target = _int(args.get('target'))
            return ("SELECT 1 FROM users WHERE id=? AND role<>'owner' AND status='active'", (target,),
                    [("UPDATE users SET status='disabled' WHERE id=?", (target,)),
                     ('DELETE FROM sessions WHERE user_id=?', (target,)),
                     ("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target,)),
                     audit('ai_work_user_disable', '工作模式注销账号', target)])
        if name == 'user_revoke':
            target = _int(args.get('target'))
            return ("SELECT 1 FROM users WHERE id=? AND role<>'owner' AND status='active'", (target,),
                    [('DELETE FROM sessions WHERE user_id=?', (target,)),
                     audit('ai_work_user_revoke', '工作模式强制下线', target)])
        if name == 'user_ban':
            target = _int(args.get('target'))
            banned = bool(args.get('banned'))
            t = await self.db.first('SELECT id,status FROM users WHERE id=?', (target,))
            if not banned:
                require(t['status'] == 'banned', '该账号当前不是封禁状态，无法解封')
            guard = 'SELECT 1 FROM users WHERE id=? AND role<>\'owner\' AND status=?'
            stmts = []
            if banned:
                has_orders = await self.db.scalar('SELECT COUNT(*) FROM orders WHERE buyer_id=? OR seller_id=?', (target, target))
                if has_orders:
                    stmts.extend(self.cf_staff_ban_order_statements(target, now))
                stmts.extend([('DELETE FROM sessions WHERE user_id=?', (target,)),
                              ("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target,))])
            stmts.append(("UPDATE users SET status=? WHERE id=?", ('banned' if banned else 'active', target)))
            stmts.append(audit('ai_work_ban' if banned else 'ai_work_unban',
                               str(args.get('reason') or '工作模式封禁'), target))
            return guard, (target, t['status']), stmts
        if name == 'user_credit':
            target = _int(args.get('target')); delta = int(args['delta']); tid = _int(args.get('ticket'))
            guard = ("SELECT 1 FROM users WHERE id=? AND role<>'owner' AND status='active' "
                     "AND EXISTS(SELECT 1 FROM tickets WHERE id=? AND status='resolved')")
            return guard, (target, tid), [
                    ('UPDATE users SET score=MAX(0,MIN(100,score+?)) WHERE id=?', (delta, target)),
                    audit('ai_work_credit', str(args.get('reason') or '工作模式调整信誉'), target, tid, delta),
                    self.cf_staff_notify(target, 'credit', '你的信誉分有变动（%+d 分），可查看依据并申诉。' % delta, tid=tid)]
        if name == 'product_moderate':
            pid = _int(args.get('id'))
            p = await self.db.first('SELECT id,seller_id,status,promoted_until FROM products WHERE id=?', (pid,))
            action = args.get('action'); reason = str(args.get('reason') or '工作模式处置')
            return ('SELECT 1 FROM products WHERE id=? AND status=? AND seller_id=?', (pid, p['status'], p['seller_id']),
                    [('UPDATE products SET status=?,delisted_by=?,promoted_until=? WHERE id=?',
                      ('removed' if action == 'delist' else 'available', uid if action == 'delist' else 0,
                       0 if action == 'delist' else (p['promoted_until'] or 0), pid)),
                     audit('ai_work_product_moderate', '%s商品 #%s：%s' % ('下架' if action == 'delist' else '恢复', pid, reason)),
                     self.cf_staff_notify(p['seller_id'], 'product_moderate',
                                          '你的商品 #%d 已被平台%s。理由：%s' % (pid, '下架' if action == 'delist' else '恢复', reason))])
        if name == 'product_promote':
            pid = _int(args.get('id'))
            days = {'1d': 1, '3d': 3, '7d': 7}[args.get('tier')]
            return ("SELECT 1 FROM products WHERE id=? AND status='available'", (pid,),
                    [('UPDATE products SET promoted_until=MAX(COALESCE(promoted_until,0),?)+? WHERE id=?', (now, days * 86400, pid)),
                     audit('ai_work_promote', '工作模式置顶 %d 天：%s' % (days, args.get('reason') or ''), pid)])
        if name == 'product_batch_delist':
            seller = _int(args.get('seller'))
            reason = str(args.get('reason') or '工作模式整店下架')
            rows = await self.db.all("SELECT id FROM products WHERE seller_id=? AND status='available' ORDER BY id LIMIT 100", (seller,))
            require(rows, '该卖家当前没有在售商品可下架')
            ids = [r['id'] for r in rows]; encoded = json.dumps(ids)
            # 用 json_each 传 id 集合而不是 N 个占位符：D1 单语句绑定参数上限 100，
            # 卖家在售商品可以远超这个数；参照 cf_staff_delist 的同一写法。
            guard = ("SELECT 1 WHERE (SELECT COUNT(*) FROM products WHERE seller_id=? AND status='available')=? "
                     "AND NOT EXISTS(SELECT 1 FROM json_each(?) j LEFT JOIN products p ON p.id=j.value "
                     "WHERE p.id IS NULL OR p.seller_id<>? OR p.status<>'available')")
            return guard, (seller, len(ids), encoded, seller), [
                ("UPDATE products SET status='removed',delisted_by=?,promoted_until=0 WHERE seller_id=? AND status='available'", (uid, seller)),
                audit('ai_work_batch_delist', '整店下架 %d 件：%s' % (len(ids), reason), seller),
                self.cf_staff_notify(seller, 'product_moderate',
                                     '你在售的 %d 件商品已被平台下架。理由：%s。如有异议可申诉。' % (len(ids), reason))]
        if name == 'product_bulk_moderate':
            action = args.get('action')
            sql = "SELECT id FROM products WHERE status=?"
            params = ['available' if action == 'delist' else 'removed']
            if args.get('q'):
                sql += ' AND title LIKE ?'
                params.append('%' + str(args['q']) + '%')
            if args.get('category'):
                sql += ' AND category=?'
                params.append(args['category'])
            if args.get('seller'):
                sql += ' AND seller_id=?'
                params.append(_int(args.get('seller')))
            sql += ' LIMIT 50'
            rows = await self.db.all(sql, tuple(params))
            require(rows, '没有符合条件的商品')
            ids = [r['id'] for r in rows]
            marks = ','.join('?' * len(ids))
            verb = '下架' if action == 'delist' else '恢复'
            # 下架才清零置顶；恢复上架保留卖家已购买的置顶时长。
            update = ('UPDATE products SET status=?,delisted_by=?,promoted_until=0 WHERE id IN (%s)' % marks,
                      ('removed', uid, *ids)) if action == 'delist' else \
                     ('UPDATE products SET status=?,delisted_by=0 WHERE id IN (%s)' % marks, ('available', *ids))
            return ('SELECT 1 FROM users WHERE id=? AND role=\'owner\' AND status=\'active\'', (uid,),
                    [update,
                     audit('ai_work_bulk_moderate', '按条件批量%s %d 件：%s' % (verb, len(ids), args.get('reason') or '工作模式批量处置'))])
        if name == 'content_remove':
            kind = args.get('kind')
            cid = _int(args.get('id'))
            table = 'posts' if kind == 'post' else 'messages'
            label = '帖子' if kind == 'post' else '聊天消息'
            reason = str(args.get('reason') or '工作模式移除')
            row = await self.db.first('SELECT user_id FROM %s WHERE id=?' % table, (cid,))
            require(row, '内容不存在', 404)
            require(row['user_id'] != uid, '不能处置自己发布的内容', 403)
            return ('SELECT 1 FROM %s WHERE id=?' % table, (cid,),
                    [('UPDATE %s SET removed=1 WHERE id=?' % table, (cid,)),
                     audit('ai_work_content_remove', '移除%s #%s：%s' % (label, cid, reason)),
                     self.cf_staff_notify(row['user_id'], 'content_removed',
                                          '你发布的一条%s因「%s」已被移除。如有异议可申诉。' % (label, reason))])
        if name == 'ticket_reply':
            tid = _int(args.get('id'))
            t = await self.cf_staff_ticket_dto(uid, tid)
            guard, guard_args, stmts, roles = await self.cf_staff_reply_plan(uid, t, args)
            return guard, guard_args, stmts + [audit('ai_work_ticket_reply', '工作模式回复工单 #%s' % tid, tid=tid)]
        if name == 'ticket_resolve':
            tid = _int(args.get('id'))
            t = await self.cf_staff_ticket_dto(uid, tid)
            plan = await self.cf_staff_resolve_plan(uid, t, args)
            require(plan, '该工单已结案，无需重复处理', 409)
            guard, guard_args, stmts = plan
            return guard, guard_args, stmts + [audit('ai_work_ticket_resolve', '工作模式处理工单 #%s：%s' % (tid, args.get('outcome')), tid=tid)]
        if name == 'notification_send':
            target = _int(args.get('target'))
            body = ValidationMixin.text(args.get('body'), 300, '通知内容')
            return ("SELECT 1 FROM users WHERE id=? AND status='active'", (target,),
                    [self.cf_staff_notify(target, 'work_notice', body),
                     audit('ai_work_notification', '工作模式发送通知', target)])
        if name == 'ai_settings':
            enabled = 1 if args.get('enabled') else 0
            daily = args.get('daily_limit') or 30
            staff = args.get('staff_daily_limit') or 100
            return ('SELECT 1 FROM users WHERE id=? AND role=\'owner\' AND status=\'active\'', (uid,),
                    [('INSERT OR IGNORE INTO ai_settings(id,enabled,daily_limit,staff_daily_limit) VALUES(1,1,30,100)', ()),
                     ('UPDATE ai_settings SET enabled=?,daily_limit=?,staff_daily_limit=?,updated_by=?,updated_at=? WHERE id=1',
                      (enabled, daily, staff, uid, now)),
                     audit('ai_work_ai_settings', '工作模式调整 AI 设置：%s，普通 %s/天，客服 %s/天' % (
                         '开启' if enabled else '关闭', daily, staff))])
        if name == 'demo_publish':
            items = clean_product_items(args.get('items'))
            require(items, '商品数据不合法')
            stmts = []
            ids = []
            for idx, item in enumerate(items):
                pid = secrets.randbits(48)
                ids.append(pid)
                data = {'description': item['description'], 'condition': item['condition'],
                        'virtual': True,
                        'photos': [{'url': demo_photo_for(item['category'], idx), 'angle': 'front'}]}
                stmts.append(('INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,'
                              'region,status,data,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                              (pid, uid, item['title'], item['category'], item['price'], 0, 'pickup',
                               '校内面交', 'available', json.dumps(data, ensure_ascii=False), now)))
            stmts.append(audit('ai_work_demo_publish', '工作模式生成演示商品 %d 件' % len(ids)))
            return ('SELECT 1 FROM users WHERE id=? AND role=\'owner\' AND status=\'active\'', (uid,), stmts)
        if name == 'demo_cleanup':
            rows = await self.db.all('SELECT id,data FROM products')
            ids = []
            for r in rows:
                try:
                    if json.loads(r['data'] or '{}').get('virtual'):
                        ids.append(r['id'])
                except ValueError:
                    continue
            stmts = [('DELETE FROM products WHERE id IN (%s)' % ','.join('?' * len(ids)), tuple(ids))] if ids else []
            stmts.append(audit('ai_work_demo_cleanup', '工作模式清理演示商品 %d 件' % len(ids)))
            return ('SELECT 1 FROM users WHERE id=? AND role=\'owner\' AND status=\'active\'', (uid,), stmts)
        if name == 'backup':
            # 打包必须在提交前完成（要读全库）。若守卫随后失败，最坏是多一个
            # 未被引用的备份对象，不会产生错误的业务数据。
            payload, _manifest, media = await self.cf_staff_backup_archive(uid)
            key = await self.media_store.put_backup(payload, 'huali-d1-r2-%d.zip' % int(now))
            return ('SELECT 1 FROM users WHERE id=? AND role=\'owner\' AND status=\'active\'', (uid,),
                    [audit('ai_work_backup', '工作模式创建备份 %s（%d 字节，%d 个媒体）' % (key, len(payload), media))])
        raise DomainError('未知工具', 404)


WORK_ROUTES = {
    '/api/ai/work/tools': (('GET',), 'work_tools'),
    '/api/ai/work/chat': (('POST',), 'work_chat'),
    '/api/ai/work/call': (('POST',), 'work_call'),
    '/api/ai/work/confirm': (('POST',), 'work_confirm'),
}
