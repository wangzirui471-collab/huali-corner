"""所有者办公助手 · 只读数据查询层。

为什么单独一层：
- 办公助手原来只给模型一份聚合快照（用户总数、订单数），问「把所有用户列出来」
  只能回答「这个数据我没有」。要真的能办公，得让代码按意图查库。
- 但用户名单、手机号不能交给第三方模型。所以这里所有答案都在代码里拼好，
  数据查询是确定性的；模型只负责它擅长的起草与总结。
- 只读 + 参数化：这里没有任何写操作，用户输入只进 SQL 参数，不拼字符串。
- 最小化：手机号打码；不返回聊天正文、密码、恢复码。

约定：office_lookup() 返回 {'answer', 'items', 'stats'} 或 None（没识别成数据查询）。
"""
import re
import time

CST = 8 * 3600

ROLE_CN = {'user': '普通用户', 'support': '客服', 'admin': '管理员',
           'developer': '开发者', 'owner': '平台所有者'}
ORDER_CN = {'awaiting_payment': '待付款', 'paid': '待发货', 'awaiting_handover': '待交接',
            'awaiting_receipt': '待收货', 'completed': '已完成', 'cancelled': '已取消',
            'refunded': '已退款', 'partial_refunded': '部分退款', 'disputed': '争议中'}
PRODUCT_CN = {'available': '在售', 'reserved': '已预留', 'sold': '已售出', 'removed': '已下架'}
TICKET_CN = {'open': '待处理', 'processing': '处理中', 'review': '待复核', 'resolved': '已解决'}
TICKET_TYPE_CN = {'refund': '售后', 'report': '举报', 'appeal': '申诉',
                  'reschedule': '改约', 'other': '咨询'}
USER_STATUS_CN = {'active': '正常', 'disabled': '已注销', 'banned': '已封禁'}


# --- 小工具 --------------------------------------------------------------
def day_start(offset=0):
    """北京时间某天 00:00 的 epoch。"""
    now = time.time() + CST
    return (int(now // 86400) + offset) * 86400 - CST


def fmt_time(ts):
    if not ts:
        return '—'
    return time.strftime('%m-%d %H:%M', time.gmtime(float(ts) + CST))


def mask_phone(phone):
    s = str(phone or '')
    if len(s) >= 7:
        return s[:3] + '****' + s[-4:]
    return (s[:1] + '***') if s else ''


def money(cents):
    return '¥%.2f' % (int(cents or 0) / 100)


def _like(keyword):
    s = str(keyword or '')
    s = s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return '%' + s + '%'


def _limit_of(q, default=10, cap=30):
    m = (re.search(r'(?:前|最近|最新|top)\s*(\d{1,3})', q, re.I)
         or re.search(r'(\d{1,3})\s*(?:个|条|笔|单|名|位)', q))
    n = int(m.group(1)) if m else default
    if '所有' in q or '全部' in q:
        n = cap
    return max(1, min(n, cap))


def _quoted(q):
    m = re.search(r'[「『“"]([^」』”"]{1,30})[」』”"]', q)
    return m.group(1).strip() if m else ''


def _name_after(q):
    m = re.search(r'(?:查一下|查查|查询|查找|搜索|搜一下|找一下|找找|找|看一下|看看)\s*'
                  r'([\u4e00-\u9fa5A-Za-z0-9_\-]{2,20})', q)
    if not m:
        return ''
    name = re.sub(r'^(用户|账号|会员)', '', m.group(1)).rstrip('的')
    if name in ('用户', '账号', '会员', '资料', '详情', '信息', '订单', '商品',
                '工单', '记录', '平台', '数据'):
        return ''
    return name


def _name_before_detail(q):
    """「张三的用户详情」这种把名字放在前面的说法。"""
    m = re.search(r'([\u4e00-\u9fa5A-Za-z0-9_\-]{2,12}?)(?:的)?(?:用户)?(?:详情|资料|信息|档案)', q)
    if not m:
        return ''
    name = m.group(1).rstrip('的')
    for w in ('查看', '查询', '看看', '看一下', '查一下'):
        name = name.replace(w, '')
    return '' if name in ('用户', '账号', '这个', '那个') else name


def _window(q):
    """返回 (since, until, label)；没提时间就不限。"""
    if '今天' in q or '今日' in q:
        return day_start(0), None, '今天'
    if '昨天' in q:
        return day_start(-1), day_start(0), '昨天'
    if any(w in q for w in ('近7天', '最近7天', '本周', '一周')):
        return day_start(-6), None, '近 7 天'
    if any(w in q for w in ('近30天', '最近30天', '一个月')):
        return day_start(-29), None, '近 30 天'
    if '24小时' in q or '24 小时' in q:
        return time.time() - 86400, None, '近 24 小时'
    return None, None, ''


def _add_window(where, args, since, until, col):
    if since is not None:
        where.append('%s>=?' % col)
        args.append(since)
    if until is not None:
        where.append('%s<?' % col)
        args.append(until)


def _where(parts):
    return (' WHERE ' + ' AND '.join(parts)) if parts else ''


def _role_of(q):
    for word, role in (('所有者', 'owner'), ('管理员', 'admin'), ('开发者', 'developer'),
                       ('客服', 'support'), ('普通用户', 'user')):
        if word in q:
            return role
    return None


def _user_status_of(q):
    if '封禁' in q:
        return 'banned'
    if any(w in q for w in ('停用', '禁用', '注销')):
        return 'disabled'
    if any(w in q for w in ('正常', '启用')):
        return 'active'
    return None


def _order_status_of(q):
    for word, status in (('待付款', 'awaiting_payment'), ('待发货', 'paid'),
                         ('待交接', 'awaiting_handover'), ('待收货', 'awaiting_receipt'),
                         ('已完成', 'completed'), ('已取消', 'cancelled'),
                         ('已退款', 'refunded'), ('争议', 'disputed')):
        if word in q:
            return status
    return None


def _product_status_of(q):
    for word, status in (('在售', 'available'), ('预留', 'reserved'),
                         ('已售', 'sold'), ('下架', 'removed')):
        if word in q:
            return status
    return None


def _ticket_status_of(q):
    for word, status in (('待处理', 'open'), ('处理中', 'processing'),
                         ('待复核', 'review'), ('已解决', 'resolved')):
        if word in q:
            return status
    return None


# --- 意图识别 ------------------------------------------------------------
def parse_office_query(question):
    """把办公问题解析成数据查询；识别不了返回 None，交给模型兜底。"""
    q = str(question or '').strip()
    if not q:
        return None

    if any(w in q for w in ('审计', '操作记录', '操作日志', '改动记录', '谁改')):
        return {'kind': 'audit', 'limit': _limit_of(q)}
    if any(w in q for w in ('求购', '想收')):
        return {'kind': 'wants', 'limit': _limit_of(q)}
    if any(w in q for w in ('工单', '售后单', '投诉单')):
        return {'kind': 'tickets', 'status': _ticket_status_of(q),
                'limit': _limit_of(q)}
    if any(w in q for w in ('订单', '成交', '交易', '买家', '卖家', '客单价', 'GMV', 'gmv')):
        return {'kind': 'orders', 'status': _order_status_of(q),
                'window': _window(q), 'limit': _limit_of(q)}
    if any(w in q for w in ('商品', '在售', '下架', '库存', '上架')):
        return {'kind': 'products', 'status': _product_status_of(q),
                'window': _window(q), 'limit': _limit_of(q)}
    if any(w in q for w in ('概览', '大盘', '平台数据', '统计数据', '总体', '整体情况')):
        return {'kind': 'overview'}
    if any(w in q for w in ('用户', '账号', '会员', '成员', '名单', '注册',
                            '管理员', '客服', '开发者', '所有者', '普通用户',
                            '封禁', '禁用', '停用')):
        detail = any(w in q for w in ('详情', '资料', '信息', '档案'))
        return {'kind': 'user_detail' if detail else 'users',
                'role': _role_of(q), 'status': _user_status_of(q),
                'keyword': _quoted(q) or _name_after(q) or (_name_before_detail(q) if detail else ''),
                'new': any(w in q for w in ('注册', '新增', '新用户')),
                'count_only': any(w in q for w in ('多少', '几个', '数量', '总数'))
                              and not any(w in q for w in ('列', '名单', '哪些')),
                'window': _window(q), 'limit': _limit_of(q)}
    return None


# --- 查询实现 ------------------------------------------------------------
async def _users(db, plan):
    where, args = [], []
    if plan.get('role'):
        where.append('role=?')
        args.append(plan['role'])
    if plan.get('status'):
        where.append('status=?')
        args.append(plan['status'])
    if plan.get('keyword'):
        where.append("nickname LIKE ? ESCAPE '\\'")
        args.append(_like(plan['keyword']))
    w = _where(where)
    params = tuple(args)

    total = int(await db.scalar('SELECT COUNT(*) FROM users' + w, params) or 0)
    if not total:
        cond = plan.get('keyword') or ROLE_CN.get(plan.get('role') or '') or '该条件'
        return {'answer': '没有找到符合条件的账号（%s）。' % cond, 'items': []}

    by_role = await db.all('SELECT role,COUNT(*) n FROM users' + w + ' GROUP BY role', params)
    role_txt = ' · '.join('%s %s' % (ROLE_CN.get(r['role'], r['role']), r['n']) for r in by_role)
    # users 表没有 created 列：用 ID 倒序近似「最新注册」，其余按最近登录。
    order_sql = 'id DESC' if plan.get('new') else 'last_login DESC, id DESC'
    rows = await db.all(
        'SELECT id,nickname,role,status,phone,college,grade,score,last_login '
        'FROM users' + w + ' ORDER BY ' + order_sql + ' LIMIT ?',
        params + (plan['limit'],))

    head = '共 %d 个账号（%s）' % (total, role_txt or '—')
    if plan.get('count_only'):
        return {'answer': head + '。', 'items': [], 'stats': {'users': total}}
    head += '，%s %d 个：' % ('最新注册' if plan.get('new') else '最近登录', len(rows))
    lines, items = [], []
    for i, r in enumerate(rows, 1):
        bits = ['#%s' % r['id'], ROLE_CN.get(r['role'], r['role']),
                USER_STATUS_CN.get(r['status'], r['status'])]
        sub = [' · '.join(bits)]
        if r['college']:
            sub.append(str(r['college']) + ((' ' + str(r['grade'])) if r['grade'] else ''))
        sub.append('信誉 %s' % (r['score'] if r['score'] is not None else '—'))
        sub.append(mask_phone(r['phone']))
        sub.append(('最近登录 ' + fmt_time(r['last_login'])) if not plan.get('new')
                   else ('账号 ID #%s' % r['id']))
        meta = ' · '.join([x for x in sub if x])
        lines.append('%d. %s（%s）' % (i, r['nickname'], meta))
        items.append({'title': '%s · %s' % (r['nickname'], ROLE_CN.get(r['role'], r['role'])),
                      'meta': meta})
    answer = head + '\n' + '\n'.join(lines)
    if total > len(rows):
        answer += '\n（还有 %d 个，说「前 %d 个」可以多看一些）' % (total - len(rows), min(total, 30))
    return {'answer': answer, 'items': items, 'stats': {'users': total}}


async def _user_detail(db, plan):
    key = plan.get('keyword') or ''
    m = re.search(r'#(\d+)|id\s*[:=]?\s*(\d+)', key, re.I)
    row = None
    if m:
        row = await db.first('SELECT * FROM users WHERE id=?', (int(m.group(1) or m.group(2)),))
    elif key:
        row = await db.first('SELECT * FROM users WHERE nickname=?', (key,))
        if not row:
            row = await db.first(
                "SELECT * FROM users WHERE nickname LIKE ? ESCAPE '\\' ORDER BY id LIMIT 1",
                (_like(key),))
    if not row:
        return {'answer': '没找到这个账号。请说完整昵称，或用「#用户ID」查询。', 'items': []}

    uid = row['id']
    p = await db.first('SELECT COUNT(*) n, SUM(CASE WHEN status=\'available\' THEN 1 ELSE 0 END) on_sale '
                       'FROM products WHERE seller_id=?', (uid,))
    b = await db.first('SELECT COUNT(*) n FROM orders WHERE buyer_id=?', (uid,))
    s = await db.first('SELECT COUNT(*) n FROM orders WHERE seller_id=?', (uid,))
    t = await db.first('SELECT COUNT(*) n FROM tickets WHERE user_id=?', (uid,))
    a = await db.all('SELECT type,reason,created FROM audit WHERE target=? ORDER BY id DESC LIMIT 3',
                     (uid,))
    lines = [
        '账号 #%s · %s（%s · %s）' % (uid, row['nickname'], ROLE_CN.get(row['role'], row['role']),
                                    USER_STATUS_CN.get(row['status'], row['status'])),
        '学院：%s %s · 信誉 %s/100 · 手机号 %s' % (
            row['college'] or '—', row['grade'] or '', row['score'],
            mask_phone(row['phone'])),
        '最近登录 %s' % fmt_time(row['last_login']),
        '发布商品 %s 件（在售 %s）· 买家订单 %s 笔 · 卖家订单 %s 笔 · 工单 %s 张' % (
            int(p['n'] or 0), int(p['on_sale'] or 0), int(b['n'] or 0),
            int(s['n'] or 0), int(t['n'] or 0)),
    ]
    if a:
        lines.append('最近处置：' + '；'.join(
            '%s %s' % (fmt_time(x['created']), x['reason'] or x['type']) for x in a))
    lines.append('完整手机号请到管理台档案查看。')
    return {'answer': '\n'.join(lines), 'items': [],
            'stats': {'user': {'id': uid, 'nickname': row['nickname']}}}


async def _orders(db, plan):
    since, until, label = plan.get('window') or (None, None, '')
    where, args = [], []
    _add_window(where, args, since, until, 'o.created')
    if plan.get('status'):
        where.append('o.status=?')
        args.append(plan['status'])
    w = _where(where)
    params = tuple(args)

    agg = await db.first('SELECT COUNT(*) n, COALESCE(SUM(o.total),0) amount FROM orders o' + w,
                         params)
    by = await db.all('SELECT o.status,COUNT(*) n FROM orders o' + w + ' GROUP BY o.status', params)
    rows = await db.all(
        'SELECT o.id,o.status,o.total,o.created,ub.nickname buyer,us.nickname seller '
        'FROM orders o LEFT JOIN users ub ON ub.id=o.buyer_id '
        'LEFT JOIN users us ON us.id=o.seller_id' + w +
        ' ORDER BY o.id DESC LIMIT ?', params + (plan['limit'],))

    total = int(agg['n'] or 0)
    if not total:
        return {'answer': ('%s没有订单。' % (label or '平台')), 'items': []}
    breakdown = ' · '.join('%s %s' % (ORDER_CN.get(x['status'], x['status']), x['n']) for x in by)
    head = '%s %d 笔订单，合计 %s（%s）' % (label or '平台共', total, money(agg['amount']), breakdown)
    lines, items = [head], []
    for r in rows:
        line = '#%s %s · %s · %s → %s · %s' % (
            r['id'], money(r['total']), ORDER_CN.get(r['status'], r['status']),
            r['buyer'] or '—', r['seller'] or '—', fmt_time(r['created']))
        lines.append(line)
        items.append({'title': '#%s %s · %s' % (r['id'], money(r['total']),
                                                ORDER_CN.get(r['status'], r['status'])),
                      'meta': '%s → %s · %s' % (r['buyer'] or '—', r['seller'] or '—',
                                                fmt_time(r['created']))})
    if total > len(rows):
        lines.append('（还有 %d 笔，说「前 %d 笔」可以多看一些）' % (total - len(rows), min(total, 30)))
    return {'answer': '\n'.join(lines), 'items': items,
            'stats': {'orders': {'total': total, 'amount': int(agg['amount'] or 0)}}}


async def _products(db, plan):
    since, until, label = plan.get('window') or (None, None, '')
    where, args = [], []
    _add_window(where, args, since, until, 'p.created')
    if plan.get('status'):
        where.append('p.status=?')
        args.append(plan['status'])
    w = _where(where)
    params = tuple(args)

    total = int(await db.scalar('SELECT COUNT(*) FROM products p' + w, params) or 0)
    if not total:
        return {'answer': '%s没有商品。' % (label or '平台'), 'items': []}
    by = await db.all('SELECT p.status,COUNT(*) n FROM products p' + w + ' GROUP BY p.status', params)
    rows = await db.all(
        'SELECT p.id,p.title,p.price,p.status,p.category,p.created,u.nickname seller '
        'FROM products p LEFT JOIN users u ON u.id=p.seller_id' + w +
        ' ORDER BY p.id DESC LIMIT ?', params + (plan['limit'],))
    breakdown = ' · '.join('%s %s' % (PRODUCT_CN.get(x['status'], x['status']), x['n']) for x in by)
    head = '%s共 %d 件商品（%s）' % (label or '平台', total, breakdown)
    lines, items = [head], []
    for r in rows:
        line = '%s %s · %s · 卖家 %s · %s' % (
            str(r['title'])[:30], money(r['price']),
            PRODUCT_CN.get(r['status'], r['status']), r['seller'] or '—', fmt_time(r['created']))
        lines.append(line)
        items.append({'title': str(r['title'])[:30],
                      'meta': '%s · %s · %s' % (money(r['price']),
                                                PRODUCT_CN.get(r['status'], r['status']),
                                                r['seller'] or '—')})
    if total > len(rows):
        lines.append('（还有 %d 件，说「前 %d 件」可以多看一些）' % (total - len(rows), min(total, 30)))
    return {'answer': '\n'.join(lines), 'items': items, 'stats': {'products': total}}


async def _tickets(db, plan):
    where, args = [], []
    if plan.get('status'):
        where.append('t.status=?')
        args.append(plan['status'])
    else:
        where.append("t.status IN ('open','processing','review')")
    w = _where(where)
    params = tuple(args)

    total = int(await db.scalar('SELECT COUNT(*) FROM tickets t' + w, params) or 0)
    if not total:
        return {'answer': '没有符合条件的工单。', 'items': []}
    by = await db.all('SELECT t.status,COUNT(*) n FROM tickets t' + w + ' GROUP BY t.status', params)
    rows = await db.all(
        'SELECT t.id,t.type,t.subject,t.status,t.created,u.nickname '
        'FROM tickets t LEFT JOIN users u ON u.id=t.user_id' + w +
        ' ORDER BY t.id DESC LIMIT ?', params + (plan['limit'],))
    breakdown = ' · '.join('%s %s' % (TICKET_CN.get(x['status'], x['status']), x['n']) for x in by)
    if plan.get('status'):
        head = '%s %d 张（%s）：' % (TICKET_CN.get(plan['status'], plan['status']), total, breakdown)
    else:
        head = '待处理及处理中 %d 张（%s）：' % (total, breakdown)
    lines = [head]
    items = []
    for r in rows:
        line = '#%s %s · %s · %s · %s' % (
            r['id'], TICKET_TYPE_CN.get(r['type'], r['type']), str(r['subject'] or '')[:30],
            TICKET_CN.get(r['status'], r['status']), fmt_time(r['created']))
        lines.append(line)
        items.append({'title': '#%s %s' % (r['id'], str(r['subject'] or '')[:30]),
                      'meta': '%s · %s · %s' % (TICKET_TYPE_CN.get(r['type'], r['type']),
                                                TICKET_CN.get(r['status'], r['status']),
                                                r['nickname'] or '—')})
    if total > len(rows):
        lines.append('（还有 %d 张，说「前 %d 张」可以多看一些）' % (total - len(rows), min(total, 30)))
    return {'answer': '\n'.join(lines), 'items': items, 'stats': {'tickets': total}}


async def _audit(db, plan):
    rows = await db.all(
        'SELECT a.id,a.type,a.reason,a.created,ua.nickname actor,ut.nickname target '
        'FROM audit a LEFT JOIN users ua ON ua.id=a.actor '
        'LEFT JOIN users ut ON ut.id=a.target ORDER BY a.id DESC LIMIT ?', (plan['limit'],))
    if not rows:
        return {'answer': '还没有操作记录。', 'items': []}
    lines, items = ['最近 %d 条操作：' % len(rows)], []
    for r in rows:
        line = '%s %s · %s%s' % (
            fmt_time(r['created']), r['reason'] or r['type'],
            ('操作人 ' + r['actor']) if r['actor'] else '',
            (' · 对象 ' + r['target']) if r['target'] else '')
        lines.append(line)
        items.append({'title': str(r['reason'] or r['type'])[:40],
                      'meta': '%s%s' % (('操作人 ' + r['actor']) if r['actor'] else '—',
                                        (' · 对象 ' + r['target']) if r['target'] else '')})
    return {'answer': '\n'.join(lines), 'items': items}


async def _wants(db, plan):
    rows = await db.all(
        'SELECT w.id,w.keyword,w.budget,w.status,w.created,u.nickname '
        'FROM wants w LEFT JOIN users u ON u.id=w.user_id ORDER BY w.id DESC LIMIT ?',
        (plan['limit'],))
    if not rows:
        return {'answer': '还没有求购。', 'items': []}
    lines, items = ['最近 %d 条求购：' % len(rows)], []
    for r in rows:
        line = '#%s %s · 预算 %s · %s · %s · %s' % (
            r['id'], r['keyword'], money(r['budget']),
            '求购中' if r['status'] == 'open' else '已结束',
            r['nickname'] or '—', fmt_time(r['created']))
        lines.append(line)
        items.append({'title': '#%s %s' % (r['id'], r['keyword']),
                      'meta': '预算 %s · %s · %s' % (money(r['budget']), r['nickname'] or '—',
                                                     fmt_time(r['created']))})
    return {'answer': '\n'.join(lines), 'items': items}


async def _overview(db):
    now = time.time()
    day, week = day_start(0), day_start(-6)

    u = await db.first('SELECT COUNT(*) total, '
                       'SUM(CASE WHEN last_login>=? THEN 1 ELSE 0 END) active24 FROM users',
                       (now - 86400,))
    p = await db.first("SELECT COUNT(*) total, SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) on_sale, "
                       'SUM(CASE WHEN created>=? THEN 1 ELSE 0 END) today FROM products', (day,))
    o = await db.first('SELECT COUNT(*) total, '
                       'SUM(CASE WHEN created>=? THEN 1 ELSE 0 END) today, '
                       'SUM(CASE WHEN created>=? THEN 1 ELSE 0 END) week, '
                       'COALESCE(SUM(CASE WHEN created>=? THEN total ELSE 0 END),0) gmv '
                       'FROM orders', (day, week, week))
    t = await db.first("SELECT COUNT(*) total, "
                       "SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) open, "
                       "SUM(CASE WHEN status IN ('processing','review') THEN 1 ELSE 0 END) busy "
                       'FROM tickets')
    w = await db.first("SELECT COUNT(*) n FROM wants WHERE status='open'")
    audit = await db.all('SELECT type,reason,created FROM audit ORDER BY id DESC LIMIT 3')

    stats = {
        'users': {'total': int(u['total'] or 0), 'active24': int(u['active24'] or 0)},
        'products': {'total': int(p['total'] or 0), 'available': int(p['on_sale'] or 0),
                     'today': int(p['today'] or 0)},
        'orders': {'total': int(o['total'] or 0), 'today': int(o['today'] or 0),
                   'week': int(o['week'] or 0), 'gmv7': int(o['gmv'] or 0)},
        'tickets': {'total': int(t['total'] or 0), 'open': int(t['open'] or 0),
                    'busy': int(t['busy'] or 0)},
        'wants': int(w['n'] or 0),
    }
    lines = [
        '平台概览（%s）' % fmt_time(now),
        '用户 %d（24h 活跃 %d）' % (
            stats['users']['total'], stats['users']['active24']),
        '商品 %d（在售 %d / 今天新发 %d）' % (
            stats['products']['total'], stats['products']['available'],
            stats['products']['today']),
        '订单 %d（今天 %d / 近 7 天 %d / 近 7 天成交 %s）' % (
            stats['orders']['total'], stats['orders']['today'],
            stats['orders']['week'], money(stats['orders']['gmv7'])),
        '工单 %d（待处理 %d / 处理中 %d）· 求购 %d 条' % (
            stats['tickets']['total'], stats['tickets']['open'],
            stats['tickets']['busy'], stats['wants']),
    ]
    if audit:
        lines.append('最近操作：' + '；'.join(
            '%s %s' % (fmt_time(a['created']), a['reason'] or a['type']) for a in audit))
    return {'answer': '\n'.join(lines), 'items': [], 'stats': stats}


async def office_lookup(db, question):
    """按问题查平台数据；没识别成数据查询返回 None。"""
    plan = parse_office_query(question)
    if not plan:
        return None
    kind = plan['kind']
    if kind == 'users':
        return await _users(db, plan)
    if kind == 'user_detail':
        return await _user_detail(db, plan)
    if kind == 'orders':
        return await _orders(db, plan)
    if kind == 'products':
        return await _products(db, plan)
    if kind == 'tickets':
        return await _tickets(db, plan)
    if kind == 'audit':
        return await _audit(db, plan)
    if kind == 'wants':
        return await _wants(db, plan)
    if kind == 'overview':
        return await _overview(db)
    return None
