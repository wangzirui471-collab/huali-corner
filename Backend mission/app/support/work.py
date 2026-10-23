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
    'user_role': {'title': '调整角色', 'risk': 'danger', 'desc': '把某个账号调整为 user/support/admin/developer（不能动 owner）',
                  'params': {'target': '用户 id', 'role': '目标角色'}},
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
    return {'answer': '找到 %d 个账号（手机号已打码）。' % len(rows), 'items': items,
            'data': [dict(r) for r in rows]}


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


READ = {
    'overview': _overview, 'users': _users, 'user_detail': _user_detail,
    'products': _products, 'product_detail': _product_detail,
    'orders': _orders, 'order_detail': _order_detail,
    'tickets': _tickets, 'ticket_detail': _ticket_detail,
    'audit': _audit, 'stats': _stats,
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
    raise DomainError('未知工具', 404)


def _validate(m, u, name, args):
    """写工具在“出 proposal”前就校验目标，避免给 owner 一个执行必失败的确认卡。"""
    if name in ('user_role', 'user_disable', 'user_revoke'):
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
                'token': _sign(payload), 'mode': 'rule'}
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
        tool = 'user_role' if act['kind'] == 'role' else ('user_disable' if act['kind'] == 'disable' else 'user_revoke')
        args = {'target': target['id'], 'nickname': target['nickname']}
        if tool == 'user_role':
            args['role'] = act['role']
        return call(m, u, tool, args)

    # 先让规划器选工具；模型不可用/超时再退回规则路由。
    try:
        from .ai import plan as ai_plan
        p = ai_plan(q, catalog())
        tool = p.get('tool')
        if tool in TOOLS:
            return call(m, u, tool, p.get('args') or {})
    except Exception:  # noqa: BLE001 - 规划失败不阻断工作模式
        pass

    rules = (
        (('用户', '账号', '成员', '谁'), 'users', lambda: {'q': _keyword(q)}),
        (('商品', '在售', '下架'), 'products', lambda: {'q': _keyword(q)}),
        (('订单', '成交', '退款'), 'orders', lambda: {'days': 7}),
        (('工单', '待处理', '处理中', '复核'), 'tickets', lambda: {'status': 'open' if '待处理' in q else ''}),
        (('审计', '操作记录'), 'audit', lambda: {'days': 7}),
        (('趋势', '统计'), 'stats', lambda: {'days': 7}),
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
