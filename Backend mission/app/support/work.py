"""工作模式：owner 专用的平台工具注册表 + 待确认动作。

设计原则（参照开源 Agent 平台的工具权限）：
- 读工具直接执行，返回确定性 SQL 结果，不把数据交给模型“编”；
- 写工具只生成 proposal + 一次性 token，owner 二次确认后才执行；
- 每个工具都有 risk / params / title，前端和规划器共用同一份目录；
- 全部 owner-only，执行后写审计。
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

from ..core.errors import DomainError

_SECRET = secrets.token_bytes(32)
TOKEN_TTL = 600

ROLE_LABELS = {'user': '普通用户', 'support': '客服', 'admin': '管理员',
               'developer': '开发者', 'owner': '平台所有者'}
ROLE_RANK = {'user': 0, 'support': 1, 'admin': 2, 'developer': 3, 'owner': 4}
PRODUCT_STATUS = {'available': '在售', 'reserved': '已预留', 'sold': '已售出', 'removed': '已下架'}
ORDER_STATUS = {'pending': '待付款', 'paid': '已付款', 'awaiting_handover': '待交付',
                'awaiting_receipt': '待收货', 'completed': '已完成', 'cancelled': '已取消',
                'refunded': '已退款', 'partial_refunded': '部分退款', 'disputed': '争议中'}
TICKET_STATUS = {'open': '待处理', 'processing': '处理中', 'review': '待复核',
                 'resolved': '已解决', 'rejected': '已驳回'}

# 工具目录：desc 会直接给规划器/前端看，写清楚“能做什么、参数是什么”。
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
    'product_detail': {'title': '商品详情', 'risk': 'read', 'desc': '商品 + 卖家 + 最近订单',
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
    'stats': {'title': '趋势统计', 'risk': 'read', 'desc': '最近 N 天新增用户/商品/订单/工单',
              'params': {'days': '7 或 30'}},
    'rooms': {'title': '查会话', 'risk': 'read', 'desc': '群聊/私聊/客服会话，含最近消息时间与受理人',
              'params': {'kind': 'group/private', 'support': 'true=只看客服', 'limit': '1-50'}},
    'messages': {'title': '看聊天记录', 'risk': 'read', 'desc': '指定会话的最近消息（会写 chat_view 审计）',
                 'params': {'room': '会话 id', 'limit': '1-50'}},
    'moderation': {'title': '内容治理', 'risk': 'read', 'desc': '待处理举报、被移除的帖子/评论、待审商品',
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
    'content_remove': {'title': '移除内容', 'risk': 'danger', 'desc': '移除帖子或评论',
                       'params': {'kind': 'post/comment', 'id': '内容 id', 'reason': '理由'}},
    'demo_cleanup': {'title': '清理演示商品', 'risk': 'danger', 'desc': '删除所有 virtual 演示商品', 'params': {}},
    'backup': {'title': '创建备份', 'risk': 'write', 'desc': '打包数据库与上传文件到 backups/', 'params': {}},
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
    'demo_generate': {'title': '生成演示商品预览', 'risk': 'read',
                      'desc': '按主题生成演示商品预览（不写入数据库），确认后用 demo_publish 入库',
                      'params': {'prompt': '主题词', 'count': '1-10'}},
    'demo_publish': {'title': '发布演示商品', 'risk': 'write', 'desc': '把预览项批量入库（virtual）',
                     'params': {'items': 'ai/office/generate 返回的 items'}},
}


def catalog():
    return [{'name': k, 'title': v['title'], 'desc': v['desc'], 'risk': v['risk'],
             'params': v['params']} for k, v in TOOLS.items()]


def _mask(phone):
    phone = str(phone or '')
    return phone[:3] + '****' + phone[-4:] if len(phone) >= 11 else phone


def _items(rows, fn):
    return [fn(r) for r in rows]


def _limit(value, default=20, maximum=50):
    try:
        return max(1, min(int(value or default), maximum))
    except (TypeError, ValueError):
        return default


# --- 读工具 ---------------------------------------------------------------
def _overview(m, u, a):
    now = time.time()
    since = now - 86400
    stats = {
        'users': int(m.row("SELECT COUNT(*) n FROM users WHERE status='active'")['n']),
        'active_24h': int(m.row('SELECT COUNT(DISTINCT user_id) n FROM sessions WHERE expires>?', (now,))['n']),
        'products': int(m.row("SELECT COUNT(*) n FROM products WHERE status='available'")['n']),
        'orders_24h': int(m.row('SELECT COUNT(*) n FROM orders WHERE created>=?', (since,))['n']),
        'tickets_open': int(m.row("SELECT COUNT(*) n FROM tickets WHERE status='open'")['n']),
        'tickets_processing': int(m.row("SELECT COUNT(*) n FROM tickets WHERE status IN ('processing','review')")['n']),
    }
    answer = ('平台概览：活跃用户 {users}（24h {active_24h}），在售商品 {products}，'
              '24h 订单 {orders_24h}，待处理工单 {tickets_open}，处理中 {tickets_processing}。').format(**stats)
    return {'answer': answer, 'items': [{'title': k, 'meta': str(v)} for k, v in stats.items()], 'data': stats}


def _users(m, u, a):
    sql = 'SELECT id,nickname,role,status,phone,college,score FROM users WHERE 1=1'
    args = []
    q = str(a.get('q') or '').strip()
    if q:
        sql += ' AND (nickname LIKE ? OR phone LIKE ?)'
        args += ['%' + q + '%', '%' + q + '%']
    if a.get('role'):
        sql += ' AND role=?'
        args.append(a['role'])
    if a.get('status'):
        sql += ' AND status=?'
        args.append(a['status'])
    sql += ' ORDER BY id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 20))
    rows = m.rows(sql, tuple(args))
    items = [{'title': r['nickname'], 'meta': '%s · %s · %s · %s分' % (
        ROLE_LABELS.get(r['role'], r['role']), r['status'], _mask(r['phone']), r['score'])} for r in rows]
    return {'answer': '找到 %d 个账号（手机号已打码，需要全号请查用户详情）。' % len(rows), 'items': items,
            'data': [dict(r, phone=_mask(r['phone'])) for r in rows]}


def _user_detail(m, u, a):
    uid = int(a.get('id') or 0)
    r = m.row('SELECT id,nickname,role,status,phone,college,major,score,created FROM users WHERE id=?', (uid,))
    if not r:
        raise DomainError('用户不存在', 404)
    reveal = bool(a.get('reveal'))
    data = dict(r)
    data['phone'] = r['phone'] if reveal else _mask(r['phone'])
    if reveal:
        with m.tx() as c:
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, uid, 'pii_view', '工作模式查看完整手机号', time.time()))
    data['products'] = int(m.row('SELECT COUNT(*) n FROM products WHERE seller_id=?', (uid,))['n'])
    data['orders'] = int(m.row('SELECT COUNT(*) n FROM orders WHERE buyer_id=? OR seller_id=?', (uid, uid))['n'])
    data['tickets'] = int(m.row('SELECT COUNT(*) n FROM tickets WHERE user_id=?', (uid,))['n'])
    recent = m.rows('SELECT id,title,price,status FROM products WHERE seller_id=? ORDER BY id DESC LIMIT 5', (uid,))
    items = [{'title': '#%s %s' % (p['id'], p['title']), 'meta': '%s · ¥%.2f' % (
        PRODUCT_STATUS.get(p['status'], p['status']), int(p['price']) / 100)} for p in recent]
    return {'answer': '用户「%s」：%s，%s，%s分；商品 %d，订单 %d，工单 %d。' % (
        r['nickname'], ROLE_LABELS.get(r['role'], r['role']), r['status'], r['score'],
        data['products'], data['orders'], data['tickets']), 'items': items, 'data': data}


def _products(m, u, a):
    sql = ('SELECT p.id,p.title,p.category,p.price,p.status,p.seller_id,p.created,u.nickname '
           'FROM products p JOIN users u ON u.id=p.seller_id WHERE 1=1')
    args = []
    if a.get('q'):
        sql += ' AND p.title LIKE ?'
        args.append('%' + str(a['q']) + '%')
    if a.get('category'):
        sql += ' AND p.category=?'
        args.append(a['category'])
    if a.get('status'):
        sql += ' AND p.status=?'
        args.append(a['status'])
    if a.get('seller'):
        sql += ' AND p.seller_id=?'
        args.append(int(a['seller']))
    sql += ' ORDER BY p.id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 20))
    rows = m.rows(sql, tuple(args))
    items = [{'title': '#%s %s' % (r['id'], r['title']), 'meta': '%s · %s · ¥%.2f · %s' % (
        r['category'], r['nickname'], int(r['price']) / 100, PRODUCT_STATUS.get(r['status'], r['status']))}
        for r in rows]
    return {'answer': '找到 %d 件商品。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _product_detail(m, u, a):
    pid = int(a.get('id') or 0)
    r = m.row('SELECT p.*,u.nickname FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?', (pid,))
    if not r:
        raise DomainError('商品不存在', 404)
    data = dict(r)
    data.pop('data', None)
    orders = []
    for o in m.rows('SELECT id,buyer_id,status,total,created,items FROM orders ORDER BY id DESC LIMIT 100'):
        try:
            items = json.loads(o['items'] or '[]')
        except ValueError:
            items = []
        if any(int(p.get('id') or 0) == pid for p in items):
            orders.append(o)
        if len(orders) >= 5:
            break
    return {'answer': '商品「%s」：%s，%s，¥%.2f，卖家 %s。' % (
        r['title'], r['category'], PRODUCT_STATUS.get(r['status'], r['status']), int(r['price']) / 100, r['nickname']),
        'items': [{'title': '订单 #%s' % o['id'], 'meta': '%s · ¥%.2f' % (
            ORDER_STATUS.get(o['status'], o['status']), int(o['total']) / 100)} for o in orders],
        'data': data}


def _orders(m, u, a):
    sql = ('SELECT o.id,o.buyer_id,o.seller_id,o.status,o.total,o.created,b.nickname buyer,s.nickname seller '
           'FROM orders o JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE 1=1')
    args = []
    if a.get('status'):
        sql += ' AND o.status=?'
        args.append(a['status'])
    if a.get('buyer'):
        sql += ' AND o.buyer_id=?'
        args.append(int(a['buyer']))
    if a.get('seller'):
        sql += ' AND o.seller_id=?'
        args.append(int(a['seller']))
    if a.get('days'):
        sql += ' AND o.created>=?'
        args.append(time.time() - int(a['days']) * 86400)
    sql += ' ORDER BY o.id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 20))
    rows = m.rows(sql, tuple(args))
    items = [{'title': '订单 #%s' % r['id'], 'meta': '%s · %s → %s · ¥%.2f' % (
        ORDER_STATUS.get(r['status'], r['status']), r['buyer'], r['seller'], int(r['total']) / 100)} for r in rows]
    return {'answer': '找到 %d 笔订单。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _order_detail(m, u, a):
    oid = int(a.get('id') or 0)
    r = m.row('SELECT o.*,b.nickname buyer,s.nickname seller FROM orders o '
              'JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id WHERE o.id=?', (oid,))
    if not r:
        raise DomainError('订单不存在', 404)
    data = dict(r)
    try:
        data['items'] = json.loads(r['items'] or '[]')
    except ValueError:
        data['items'] = []
    return {'answer': '订单 #%s：%s，%s → %s，¥%.2f。' % (
        oid, ORDER_STATUS.get(r['status'], r['status']), r['buyer'], r['seller'], int(r['total']) / 100),
        'items': [{'title': p.get('title') or '商品', 'meta': '¥%.2f' % (int(p.get('price') or 0) / 100)}
                  for p in data['items']], 'data': data}


def _tickets(m, u, a):
    sql = ('SELECT t.id,t.type,t.subject,t.status,t.user_id,t.created,u.nickname '
           'FROM tickets t JOIN users u ON u.id=t.user_id WHERE 1=1')
    args = []
    if a.get('status'):
        sql += ' AND t.status=?'
        args.append(a['status'])
    if a.get('type'):
        sql += ' AND t.type=?'
        args.append(a['type'])
    if a.get('q'):
        sql += ' AND (t.subject LIKE ? OR t.body LIKE ?)'
        args += ['%' + str(a['q']) + '%', '%' + str(a['q']) + '%']
    sql += ' ORDER BY t.id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 20))
    rows = m.rows(sql, tuple(args))
    items = [{'title': '#%s %s' % (r['id'], r['subject']), 'meta': '%s · %s · %s · %s' % (
        r['type'], TICKET_STATUS.get(r['status'], r['status']), r['nickname'], time.strftime('%m-%d %H:%M', time.localtime(r['created'])))}
        for r in rows]
    return {'answer': '找到 %d 张工单。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _ticket_detail(m, u, a):
    tid = int(a.get('id') or 0)
    r = m.row('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?', (tid,))
    if not r:
        raise DomainError('工单不存在', 404)
    msgs = m.rows('SELECT m.id,m.user_id,m.body,m.internal,m.created,u.nickname FROM ticket_messages m '
                  'JOIN users u ON u.id=m.user_id WHERE m.ticket_id=? ORDER BY m.id', (tid,))
    data = dict(r)
    data['messages'] = [dict(x) for x in msgs]
    return {'answer': '工单 #%s「%s」：%s，%s 提交，共 %d 条消息。' % (
        tid, r['subject'], TICKET_STATUS.get(r['status'], r['status']), r['nickname'], len(msgs)),
        'items': [{'title': ('内部' if x['internal'] else '公开') + ' · ' + x['nickname'],
                   'meta': str(x['body'])[:60]} for x in msgs], 'data': data}


def _audit(m, u, a):
    sql = 'SELECT id,actor,target,type,delta,reason,ticket_id,created FROM audit WHERE 1=1'
    args = []
    if a.get('actor'):
        sql += ' AND actor=?'
        args.append(int(a['actor']))
    if a.get('type'):
        sql += ' AND type=?'
        args.append(a['type'])
    if a.get('days'):
        sql += ' AND created>=?'
        args.append(time.time() - int(a['days']) * 86400)
    sql += ' ORDER BY id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 50, 100))
    rows = m.rows(sql, tuple(args))
    items = [{'title': '#%s %s' % (r['id'], r['type']), 'meta': '%s · actor %s · target %s' % (
        str(r['reason'] or '')[:40], r['actor'], r['target'])} for r in rows]
    return {'answer': '最近 %d 条审计记录。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _stats(m, u, a):
    try:
        days = max(1, min(int(a.get('days') or 7), 30))
    except (TypeError, ValueError):
        days = 7
    since = time.time() - days * 86400

    def by_day(rows):
        out = {}
        for r in rows:
            key = time.strftime('%m-%d', time.localtime(r['created']))
            out[key] = out.get(key, 0) + 1
        return out

    # users 表没有 created 列（SQLite），只给当前活跃总数；不伪造时间序列。
    users_total = int(m.row("SELECT COUNT(*) n FROM users WHERE status='active'")['n'])
    orders = by_day(m.rows('SELECT created FROM orders WHERE created>=?', (since,)))
    tickets = by_day(m.rows('SELECT created FROM tickets WHERE created>=?', (since,)))
    items = [{'title': d, 'meta': '订单 %s · 工单 %s' % (orders.get(d, 0), tickets.get(d, 0))}
             for d in sorted(set(orders) | set(tickets))]
    return {'answer': '最近 %d 天新增：订单 %d，工单 %d；当前活跃用户 %d。' % (
        days, sum(orders.values()), sum(tickets.values()), users_total), 'items': items,
        'data': {'users_total': users_total, 'orders': orders, 'tickets': tickets}}



def _rooms(m, u, a):
    sql = ("SELECT r.id,r.kind,r.name,r.support,r.assignee,r.ticket_id,r.support_status,r.college,"
           "(SELECT MAX(created) FROM messages x WHERE x.room_id=r.id) last_at FROM rooms r WHERE 1=1")
    args = []
    if a.get('kind'):
        sql += ' AND r.kind=?'
        args.append(a['kind'])
    if str(a.get('support')).lower() in ('1', 'true'):
        sql += ' AND r.support=1'
    sql += ' ORDER BY COALESCE(last_at,0) DESC, r.id DESC LIMIT ?'
    args.append(_limit(a.get('limit'), 20))
    rows = m.rows(sql, tuple(args))
    items = []
    for r in rows:
        who = '客服' if r['support'] else ('受理人 #%s' % r['assignee'] if r['assignee'] else '未分配')
        last = time.strftime('%m-%d %H:%M', time.localtime(r['last_at'])) if r['last_at'] else '无消息'
        items.append({'title': r['name'] or ('会话 #%s' % r['id']),
                      'meta': '%s · %s%s · 最近 %s' % (r['kind'], who,
                                                     (' · ' + r['support_status']) if r['support'] else '', last)})
    return {'answer': '找到 %d 个会话。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _messages(m, u, a):
    rid = int(a.get('room') or 0)
    room = m.row('SELECT id,name,kind,support FROM rooms WHERE id=?', (rid,))
    if not room:
        raise DomainError('会话不存在', 404)
    with m.tx() as c:
        c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                  (u, rid, 'chat_view', '工作模式查看聊天记录', time.time()))
    rows = list(reversed(m.rows(
        'SELECT m.id,m.user_id,m.body,m.removed,m.created,usr.nickname FROM messages m '
        'JOIN users usr ON usr.id=m.user_id WHERE m.room_id=? ORDER BY m.id DESC LIMIT ?',
        (rid, _limit(a.get('limit'), 20)))))
    items = [{'title': r['nickname'], 'meta': str(r['body'])[:80]} for r in rows]
    return {'answer': '会话「%s」最近 %d 条消息（已记录查看审计）。' % (
        room['name'] or ('#%s' % rid), len(rows)), 'items': items, 'data': [dict(r) for r in rows]}


def _moderation(m, u, a):
    lim = _limit(a.get('limit'), 10)
    reports = m.rows("SELECT id,subject,status,created FROM tickets WHERE type='report' "
                     "AND status IN ('open','processing','review') ORDER BY id DESC LIMIT ?", (lim,))
    posts = m.rows('SELECT id,substr(body,1,60) body,created FROM posts WHERE removed=1 ORDER BY id DESC LIMIT 5')
    comments = m.rows('SELECT id,post_id,substr(body,1,60) body,created FROM comments WHERE removed=1 ORDER BY id DESC LIMIT 5')
    items = [{'title': '#%s %s' % (r['id'], r['subject']), 'meta': '举报 · ' + r['status']} for r in reports]
    items += [{'title': '帖子 #%s' % r['id'], 'meta': str(r['body'])[:50]} for r in posts]
    items += [{'title': '评论 #%s' % r['id'], 'meta': str(r['body'])[:50]} for r in comments]
    return {'answer': '待处理举报 %d 条，已移除帖子 %d 条、评论 %d 条。' % (len(reports), len(posts), len(comments)),
            'items': items, 'data': {'reports': [dict(r) for r in reports], 'posts': [dict(r) for r in posts],
                                     'comments': [dict(r) for r in comments]}}


def _credit(m, u, a):
    try:
        threshold = max(0, min(int(a.get('threshold') or 80), 100))
    except (TypeError, ValueError):
        threshold = 80
    low = m.rows("SELECT id,nickname,score,status FROM users WHERE score<=? AND status='active' "
                 "ORDER BY score,id LIMIT ?", (threshold, _limit(a.get('limit'), 20)))
    recent = m.rows("SELECT id,actor,target,delta,reason,created FROM audit WHERE type='credit' "
                    "ORDER BY id DESC LIMIT 8")
    items = [{'title': r['nickname'], 'meta': '%s 分 · #%s' % (r['score'], r['id'])} for r in low]
    items += [{'title': '信誉变动 #%s' % r['id'], 'meta': '%+d · %s' % (r['delta'] or 0, str(r['reason'])[:30])}
              for r in recent]
    return {'answer': '信誉 ≤ %d 的活跃账号 %d 个；最近信誉变动 %d 条。' % (threshold, len(low), len(recent)),
            'items': items, 'data': {'low': [dict(r) for r in low], 'recent': [dict(r) for r in recent]}}


def _offers(m, u, a):
    rows = m.rows('SELECT o.id,o.product_id,o.buyer_id,o.amount,o.status,o.created,p.title,u.nickname '
                  'FROM offers o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id '
                  'ORDER BY o.id DESC LIMIT ?', (_limit(a.get('limit'), 20),))
    items = [{'title': '#%s %s' % (r['id'], r['title']), 'meta': '%s · ¥%.2f · %s' % (
        r['nickname'], int(r['amount']) / 100, r['status'])} for r in rows]
    return {'answer': '最近 %d 条出价记录。' % len(rows), 'items': items, 'data': [dict(r) for r in rows]}


def _posts(m, u, a):
    q = str(a.get('q') or '').strip()
    lim = _limit(a.get('limit'), 20)
    if q:
        posts = m.rows('SELECT id,user_id,substr(body,1,80) body,removed,created FROM posts '
                       'WHERE body LIKE ? ORDER BY id DESC LIMIT ?', ('%' + q + '%', lim))
        comments = m.rows('SELECT id,post_id,substr(body,1,80) body,removed,created FROM comments '
                          'WHERE body LIKE ? ORDER BY id DESC LIMIT ?', ('%' + q + '%', lim))
    else:
        posts = m.rows('SELECT id,user_id,substr(body,1,80) body,removed,created FROM posts ORDER BY id DESC LIMIT ?', (lim,))
        comments = m.rows('SELECT id,post_id,substr(body,1,80) body,removed,created FROM comments ORDER BY id DESC LIMIT ?', (lim,))
    items = [{'title': '帖子 #%s' % r['id'], 'meta': ('已移除 · ' if r['removed'] else '') + str(r['body'])[:50]} for r in posts]
    items += [{'title': '评论 #%s' % r['id'], 'meta': ('已移除 · ' if r['removed'] else '') + str(r['body'])[:50]} for r in comments]
    return {'answer': '找到帖子 %d 条、评论 %d 条。' % (len(posts), len(comments)), 'items': items,
            'data': {'posts': [dict(r) for r in posts], 'comments': [dict(r) for r in comments]}}


def _ledger(m, u, a):
    sums = m.rows('SELECT kind,SUM(amount) total,COUNT(*) n FROM ledger GROUP BY kind ORDER BY kind')
    recent = m.rows('SELECT id,order_id,kind,amount,created FROM ledger ORDER BY id DESC LIMIT 10')
    items = [{'title': r['kind'], 'meta': '%d 笔 · ¥%.2f' % (r['n'], int(r['total']) / 100)} for r in sums]
    items += [{'title': '流水 #%s' % r['id'], 'meta': '%s · ¥%.2f · 订单 #%s' % (
        r['kind'], int(r['amount']) / 100, r['order_id'])} for r in recent]
    return {'answer': '账本共 %d 种类型；最近 %d 条流水。' % (len(sums), len(recent)), 'items': items,
            'data': {'sums': [dict(r) for r in sums], 'recent': [dict(r) for r in recent]}}


def _sellers(m, u, a):
    try:
        days = max(1, min(int(a.get('days') or 7), 90))
    except (TypeError, ValueError):
        days = 7
    since = time.time() - days * 86400
    rows = m.rows("SELECT o.seller_id,COUNT(*) n,SUM(o.total) gmv,u.nickname FROM orders o "
                  "JOIN users u ON u.id=o.seller_id WHERE o.status='completed' AND o.created>=? "
                  "GROUP BY o.seller_id ORDER BY gmv DESC LIMIT ?", (since, _limit(a.get('limit'), 10)))
    items = [{'title': r['nickname'], 'meta': '%d 单 · ¥%.2f' % (r['n'], int(r['gmv']) / 100)} for r in rows]
    return {'answer': '最近 %d 天成交卖家 %d 位。' % (days, len(rows)), 'items': items,
            'data': [dict(r) for r in rows]}


def _demo_generate(m, u, a):
    """生成演示商品预览：规则生成、不写库；确认后用 demo_publish 入库。"""
    from . import office
    prompt = str(a.get('prompt') or '').strip()[:16] or '校园好物'
    try:
        count = max(1, min(int(a.get('count') or 5), 10))
    except (TypeError, ValueError):
        count = 5
    items = office.generate(prompt, count)
    rows = [{'title': it['title'], 'meta': '¥%.2f · %s' % (it['price'] / 100, it['condition'])}
            for it in items]
    return {'answer': '已生成 %d 件「%s」演示商品预览（尚未入库）。说「确认入库」或点确认后才会写入。' % (len(items), prompt),
            'items': rows, 'data': {'items': items, 'prompt': prompt}}


READ = {
    'overview': _overview, 'users': _users, 'user_detail': _user_detail,
    'products': _products, 'product_detail': _product_detail,
    'orders': _orders, 'order_detail': _order_detail,
    'tickets': _tickets, 'ticket_detail': _ticket_detail,
    'audit': _audit, 'stats': _stats,
    'rooms': _rooms, 'messages': _messages, 'moderation': _moderation,
    'credit': _credit, 'offers': _offers, 'posts': _posts,
    'ledger': _ledger, 'sellers': _sellers, 'demo_generate': _demo_generate,
}


# --- 写工具：proposal + 一次性 token ---------------------------------------
def _sign(payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()).decode()
    sig = hmac.new(_SECRET, raw.encode(), hashlib.sha256).hexdigest()
    return raw + '.' + sig


def _verify(token):
    try:
        raw, sig = str(token).split('.', 1)
    except ValueError:
        raise DomainError('确认令牌无效', 400) from None
    if not hmac.compare_digest(sig, hmac.new(_SECRET, raw.encode(), hashlib.sha256).hexdigest()):
        raise DomainError('确认令牌无效', 400)
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
    except Exception:  # noqa: BLE001
        raise DomainError('确认令牌无效', 400) from None
    if payload.get('exp', 0) < time.time():
        raise DomainError('确认已过期，请重新发起', 409)
    return payload


def _who(args):
    return args.get('nickname') or ('#%s' % args.get('target'))


def _summary(name, args):
    if name == 'user_role':
        return '把「%s」调整为%s，并撤销其登录会话' % (_who(args), ROLE_LABELS.get(args.get('role'), args.get('role')))
    if name == 'user_disable':
        return '注销「%s」，下架其在售商品并撤销会话' % _who(args)
    if name == 'user_revoke':
        return '强制「%s」下线（撤销全部会话）' % _who(args)
    if name == 'product_moderate':
        return '%s商品 #%s：%s' % ('恢复' if args.get('action') == 'restore' else '下架', args.get('id'), args.get('reason'))
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
    if name == 'user_ban':
        return '%s「%s」' % ('封禁' if args.get('banned') else '解封', _who(args))
    if name == 'user_credit':
        return '把「%s」的信誉分调整 %+d（工单 #%s）' % (_who(args), int(args.get('delta') or 0), args.get('ticket'))
    if name == 'product_promote':
        return '把商品 #%s 置顶 %s' % (args.get('id'), args.get('tier'))
    if name == 'product_bulk_moderate':
        if args.get('action') not in ('delist', 'restore'):
            raise DomainError('批量动作必须是 delist 或 restore', 400)
        if not any(args.get(k) for k in ('q', 'category', 'seller')):
            raise DomainError('批量处置至少要给一个筛选条件（关键词/分类/卖家）', 400)
    if name == 'product_batch_delist':
        return '下架卖家 #%s 的全部在售商品' % args.get('seller')
    if name == 'product_bulk_moderate':
        verb = '恢复' if args.get('action') == 'restore' else '下架'
        cond = '、'.join('%s=%s' % (k, args.get(k)) for k in ('q', 'category', 'seller') if args.get(k))
        return '按条件批量%s商品（%s，最多 50 件）' % (verb, cond)
    if name == 'content_remove':
        return '移除%s #%s' % ('帖子' if args.get('kind') == 'post' else '评论', args.get('id'))
    if name == 'demo_cleanup':
        return '删除全部演示商品（virtual）'
    if name == 'backup':
        return '创建一份完整备份'
    return name


def _execute(m, u, name, args):
    if name == 'user_role':
        target = int(args.get('target') or 0)
        return m.change_role(u, {'target': target, 'role': args.get('role')})
    if name == 'user_disable':
        target = int(args.get('target') or 0)
        t = m.row('SELECT id,nickname,role FROM users WHERE id=?', (target,))
        if not t:
            raise DomainError('账号不存在', 404)
        if t['role'] == 'owner':
            raise DomainError('所有者账号不能注销', 403)
        if target == u:
            raise DomainError('不能注销自己', 403)
        with m.tx() as c:
            c.execute("UPDATE users SET status='disabled' WHERE id=?", (target,))
            c.execute('DELETE FROM sessions WHERE user_id=?', (target,))
            c.execute("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, target, 'ai_work_user_disable', '工作模式注销账号', time.time()))
        return {'ok': True, 'message': '已注销「%s」' % t['nickname']}
    if name == 'user_revoke':
        return m.revoke_sessions(u, int(args.get('target') or 0))
    if name == 'product_moderate':
        return m.moderate_product(u, int(args.get('id') or 0), args.get('action'), args.get('reason') or '工作模式处置')
    if name == 'ticket_reply':
        return m.reply_ticket(u, int(args.get('id') or 0), {'body': args.get('body'), 'internal': bool(args.get('internal'))})
    if name == 'ticket_resolve':
        data = {'outcome': args.get('outcome'), 'reason': args.get('reason')}
        if args.get('amount') is not None:
            data['amount'] = args['amount']
        return m.resolve_ticket(u, int(args.get('id') or 0), data)
    if name == 'notification_send':
        target = int(args.get('target') or 0)
        body = m.text(args.get('body'), 300, '通知内容')
        with m.tx() as c:
            c.execute('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)',
                      (target, 'work_notice', body, time.time()))
        return {'ok': True, 'message': '已发送通知'}
    if name == 'ai_settings':
        return m.ai_admin_update(u, args)
    if name == 'demo_publish':
        return m.ai_office_publish(u, args.get('items'))
    if name == 'user_ban':
        target = int(args.get('target') or 0)
        banned = bool(args.get('banned'))
        m.ban_user(u, target, banned, str(args.get('reason') or '工作模式封禁'))
        return {'ok': True, 'message': '已%s' % ('解封' if not banned else '封禁')}
    if name == 'user_credit':
        m.credit_action(u, int(args.get('target') or 0), int(args.get('delta')),
                        str(args.get('reason') or '工作模式调整信誉'), int(args.get('ticket') or 0))
        return {'ok': True}
    if name == 'product_promote':
        pid = int(args.get('id') or 0)
        days = {'1d': 1, '3d': 3, '7d': 7}[args.get('tier')]
        p = m.row('SELECT id,promoted_until,status FROM products WHERE id=?', (pid,))
        if not p or p['status'] != 'available':
            raise DomainError('只有在售商品可以置顶', 400)
        until = max(p['promoted_until'] or 0, time.time()) + days * 86400
        with m.tx() as c:
            c.execute('UPDATE products SET promoted_until=? WHERE id=?', (until, pid))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, pid, 'promote', '工作模式置顶 %d 天：%s' % (days, args.get('reason') or ''), time.time()))
        return {'ok': True, 'promoted_until': until}
    if name == 'product_bulk_moderate':
        action = args.get('action')
        status = 'available' if action == 'delist' else 'removed'
        sql = 'SELECT id FROM products WHERE status=?'
        params = [status]
        if args.get('q'):
            sql += ' AND title LIKE ?'
            params.append('%' + str(args['q']) + '%')
        if args.get('category'):
            sql += ' AND category=?'
            params.append(args['category'])
        if args.get('seller'):
            sql += ' AND seller_id=?'
            params.append(int(args['seller']))
        sql += ' LIMIT 50'
        rows = m.rows(sql, tuple(params))
        count = 0
        for r in rows:
            try:
                m.moderate_product(u, r['id'], action, str(args.get('reason') or '工作模式批量处置'))
                count += 1
            except DomainError:
                pass
        return {'ok': True, 'count': count}
    if name == 'product_batch_delist':
        seller = int(args.get('seller') or 0)
        reason = str(args.get('reason') or '工作模式整店下架')
        rows = m.rows("SELECT id FROM products WHERE seller_id=? AND status='available' LIMIT 100", (seller,))
        count = 0
        for r in rows:
            try:
                m.moderate_product(u, r['id'], 'delist', reason)
                count += 1
            except DomainError:
                pass
        return {'ok': True, 'count': count}
    if name == 'content_remove':
        kind = args.get('kind')
        cid = int(args.get('id') or 0)
        table = 'posts' if kind == 'post' else 'comments'
        reason = str(args.get('reason') or '工作模式移除')
        with m.tx() as c:
            c.execute('UPDATE %s SET removed=1 WHERE id=?' % table, (cid,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, cid, 'content_remove', '移除%s #%s：%s' % (kind, cid, reason), time.time()))
        return {'ok': True}
    if name == 'demo_cleanup':
        ids = []
        for r in m.rows('SELECT id,data FROM products'):
            try:
                d = json.loads(r['data'] or '{}')
            except ValueError:
                d = {}
            if d.get('virtual'):
                ids.append(r['id'])
        with m.tx() as c:
            for pid in ids:
                c.execute('DELETE FROM products WHERE id=?', (pid,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, None, 'ai_work_demo_cleanup', '清理演示商品 %d 件' % len(ids), time.time()))
        return {'ok': True, 'count': len(ids)}
    if name == 'backup':
        return {'ok': True, 'result': m.backup(u)}
    raise DomainError('未知工具', 404)


def _validate(m, u, name, args):
    """写工具在“出 proposal”前就校验目标，避免给 owner 一个执行必失败的确认卡。"""
    if name in ('user_role', 'user_disable', 'user_revoke', 'user_ban', 'user_credit'):
        target = int(args.get('target') or 0)
        t = m.row('SELECT id,nickname,role,status FROM users WHERE id=?', (target,))
        if not t:
            raise DomainError('账号不存在', 404)
        if t['role'] == 'owner':
            raise DomainError('所有者账号不能被工作模式调整', 403)
        if target == u:
            raise DomainError('不能对自己执行此操作', 403)
    if name == 'user_role' and args.get('role') not in ('user', 'support', 'admin', 'developer'):
        raise DomainError('目标角色无效', 400)
    if name == 'product_moderate':
        if not m.row('SELECT id FROM products WHERE id=?', (int(args.get('id') or 0),)):
            raise DomainError('商品不存在', 404)
        if args.get('action') not in ('delist', 'restore'):
            raise DomainError('处置动作必须是 delist 或 restore', 400)
    if name in ('ticket_reply', 'ticket_resolve'):
        if not m.row('SELECT id FROM tickets WHERE id=?', (int(args.get('id') or 0),)):
            raise DomainError('工单不存在', 404)
    if name == 'notification_send':
        if not m.row('SELECT id FROM users WHERE id=?', (int(args.get('target') or 0),)):
            raise DomainError('收件账号不存在', 404)
    if name == 'user_credit':
        try:
            delta = int(args.get('delta'))
        except (TypeError, ValueError):
            raise DomainError('信誉变动必须是整数', 400) from None
        if delta == 0 or delta < -100 or delta > 100:
            raise DomainError('信誉变动必须在 -100 到 100 之间且不能为 0', 400)
        if not m.row('SELECT id FROM tickets WHERE id=?', (int(args.get('ticket') or 0),)):
            raise DomainError('关联工单不存在', 404)
    if name == 'product_promote':
        if not m.row('SELECT id FROM products WHERE id=?', (int(args.get('id') or 0),)):
            raise DomainError('商品不存在', 404)
        if args.get('tier') not in ('1d', '3d', '7d'):
            raise DomainError('置顶档位必须是 1d/3d/7d', 400)
    if name == 'product_batch_delist':
        if not m.row('SELECT id FROM users WHERE id=?', (int(args.get('seller') or 0),)):
            raise DomainError('卖家不存在', 404)
    if name == 'demo_publish':
        from . import office
        if not office.clean_items(args.get('items')):
            raise DomainError('商品数据不合法，请先生成预览再入库', 400)
    if name == 'content_remove':
        if args.get('kind') not in ('post', 'comment'):
            raise DomainError('内容类型必须是 post 或 comment', 400)
        table = 'posts' if args.get('kind') == 'post' else 'comments'
        if not m.row('SELECT id FROM %s WHERE id=?' % table, (int(args.get('id') or 0),)):
            raise DomainError('内容不存在', 404)


def call(m, u, name, args=None, token=None):
    if name not in TOOLS:
        raise DomainError('未知工具', 404)
    args = args if isinstance(args, dict) else {}
    spec = TOOLS[name]
    _validate(m, u, name, args)
    if spec['risk'] == 'read':
        out = READ[name](m, u, args)
        out.setdefault('tool', name)
        out.setdefault('mode', 'rule')
        return out
    if not token:
        payload = {'u': u, 'name': name, 'args': args, 'exp': int(time.time()) + TOKEN_TTL}
        return {'answer': '这是不可逆操作，请再次确认：%s。' % _summary(name, args),
                'proposal': {'tool': name, 'title': spec['title'], 'summary': _summary(name, args),
                             'risk': spec['risk'], 'args': args},
                'token': _sign(payload), 'tool': name, 'mode': 'rule'}
    payload = _verify(token)
    if payload.get('u') != u or payload.get('name') != name:
        raise DomainError('确认令牌与当前账号不匹配', 403)
    result = _execute(m, u, name, args or payload.get('args') or {})
    try:
        with open(m.root / 'ai-usage.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.time(), 'actor': u, 'channel': 'work',
                                'tool': name, 'risk': spec['risk']}, ensure_ascii=False) + '\n')
    except OSError:
        pass
    return {'ok': True, 'result': result, 'tool': name, 'mode': 'rule'}


def confirm(m, u, token):
    payload = _verify(token)
    if payload.get('u') != u:
        raise DomainError('确认令牌与当前账号不匹配', 403)
    name = payload.get('name')
    args = payload.get('args') or {}
    result = _execute(m, u, name, args)
    try:
        with open(m.root / 'ai-usage.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.time(), 'actor': u, 'channel': 'work',
                                'tool': name, 'risk': TOOLS.get(name, {}).get('risk')}, ensure_ascii=False) + '\n')
    except OSError:
        pass
    return {'ok': True, 'result': result, 'tool': name}


def agent(m, u, question):
    """规则路由器：先认账号动作，再按关键词选读工具。模型只做兜底。"""
    q = str(question or '').strip()
    from . import office
    act = office.parse_action(q)
    if act:
        target = office.resolve_target(m, act['name'])
        if not target:
            return {'answer': '没找到「%s」对应的运营账号。' % act['name'], 'items': [], 'proposal': None}
        if target['role'] == 'owner':
            return {'answer': '所有者账号不能通过助手调整，只能由运维在数据库处理。', 'items': [], 'proposal': None}
        if act['kind'] == 'role':
            tool = 'user_role'
        elif act['kind'] == 'disable':
            tool = 'user_disable'
        elif act['kind'] == 'ban':
            tool = 'user_ban'
        else:
            tool = 'user_revoke'
        args = {'target': target['id'], 'nickname': target['nickname']}
        if tool == 'user_role':
            args['role'] = act['role']
        if tool == 'user_ban':
            args.update({'banned': True, 'reason': '工作模式封禁'})
        return call(m, u, tool, args)

    # ReAct 风格多步循环：规划 → 执行读工具 → 观察结果回到规划器；
    # 写工具立即转确认卡；最多 3 步；模型不可用退回规则路由。
    observations = []
    demo_items = None
    last = None
    for _ in range(3):
        try:
            from .ai import plan as ai_plan
            p = ai_plan(q, catalog(), observations)
        except Exception:  # noqa: BLE001 - 规划失败不阻断工作模式
            break
        tool = str(p.get('tool') or '')
        if tool in ('', 'final'):
            if last:
                return last
            break
        if tool not in TOOLS:
            break
        args = p.get('args') or {}
        # 「生成预览 → 确认入库」的衔接：预览项由后端传递，不经模型转抄。
        if tool == 'demo_publish' and not args.get('items') and demo_items:
            args = dict(args, items=demo_items)
        if tool == 'demo_publish' and not args.get('items'):
            return {'answer': '还没有可入库的预览项。请说「发布 3 件宿舍好物演示商品」，我先出预览再给确认卡。',
                    'items': [], 'proposal': None, 'mode': 'rule'}
        result = call(m, u, tool, args)
        if result.get('proposal'):
            return result
        last = result
        if tool == 'demo_generate':
            demo_items = (result.get('data') or {}).get('items')
        observations.append({'tool': tool, 'args': args,
                             'answer': str(result.get('answer') or '')[:300],
                             'items': [str(i.get('title')) for i in (result.get('items') or [])][:8]})
    if last:
        return last

    # 规则兜底也让「生成预览 → 确认入库」闭环：先出预览项，再直接给确认卡，
    # 预览标题会显示在确认卡里，owner 看到清单后才点确认。
    if '演示' in q and any(w in q for w in ('发布', '入库', '上架')):
        hit = re.search(r'(\d+)\s*件', q)
        count = max(1, min(int(hit.group(1)), 10)) if hit else 5
        preview = _demo_generate(m, u, {'prompt': _keyword(q) or '校园好物', 'count': count})
        return call(m, u, 'demo_publish', {'items': (preview.get('data') or {}).get('items') or []})

    rules = (
        (('演示商品',), 'demo_generate', lambda: {'prompt': _keyword(q) or '校园好物', 'count': 5}),
        (('用户', '账号', '成员', '谁'), 'users', lambda: {'q': _keyword(q)}),
        (('商品', '在售', '下架'), 'products', lambda: {'q': _keyword(q)}),
        (('订单', '成交', '退款'), 'orders', lambda: {'days': 7}),
        (('工单', '待处理', '处理中', '复核'), 'tickets', lambda: {'status': 'open' if '待处理' in q else ''}),
        (('审计', '操作记录'), 'audit', lambda: {'days': 7}),
        (('趋势', '统计'), 'stats', lambda: {'days': 7}),
        (('会话', '聊天'), 'rooms', lambda: {}),
        (('举报', '治理', '审核'), 'moderation', lambda: {}),
        (('信誉', '低分'), 'credit', lambda: {}),
        (('议价', '出价', '还价'), 'offers', lambda: {}),
        (('帖子', '社区', '评论'), 'posts', lambda: {'q': _keyword(q)}),
        (('账本', '流水', '资金'), 'ledger', lambda: {}),
        (('排行', '卖家'), 'sellers', lambda: {'days': 7}),
    )
    for words, tool, args_fn in rules:
        if any(w in q for w in words):
            args = args_fn()
            return call(m, u, tool, {k: v for k, v in args.items() if v not in ('', None)})
    return call(m, u, 'overview', {})


def _keyword(q):
    m = re.search(r'(?:查|找|搜索|看看)\s*[「"“]?([^」"”\s，。]{1,20})', q)
    word = m.group(1) if m else ''
    return '' if word in ('用户', '账号', '成员', '商品', '订单', '工单', '审计') else word
