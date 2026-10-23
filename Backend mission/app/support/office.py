"""所有者办公助手（本地版）：确定性查询 + 待确认动作 + 演示商品预览。

与 Cloudflare 侧 `app/cloudflare/ai_support.py` 的办公接口保持同一套契约：
- 查询类问题直接用 SQL 拼答案，不把用户名单/手机号发给模型；
- 账号动作只返回 proposal，等 L1 在浏览器二次确认后才执行；
- 生成演示商品只返回预览，确认后才批量入库（virtual=1）。
"""
import re
import time
ROLE_LABELS = {'user': '普通用户', 'support': '客服', 'admin': '管理员',
               'developer': '开发者', 'owner': '平台所有者'}
ROLE_RANK = {'user': 0, 'support': 1, 'admin': 2, 'developer': 3, 'owner': 4}
CATEGORIES = ('教材书籍', '电子产品', '宿舍生活', '运动闲置')
CONDITIONS = ('全新', '几乎全新', '正常使用痕迹', '明显使用痕迹')

PHOTOS = {
    '教材书籍': ['/assets/book0.svg', '/assets/book1.svg', '/assets/book2.svg',
                 '/assets/book3.svg', '/assets/book4.svg', '/assets/book5.svg'],
    '电子产品': ['/assets/item0.svg', '/assets/item1.svg', '/assets/item2.svg'],
    '宿舍生活': ['/assets/book3.svg', '/assets/book4.svg', '/assets/book5.svg'],
    '运动闲置': ['/assets/item0.svg', '/assets/item1.svg', '/assets/item2.svg'],
}

PRODUCT_TEMPLATES = {
    '教材书籍': ('配套教材', '课后习题册', '课堂笔记', '复习提纲'),
    '电子产品': ('充电器', '耳机', '桌面支架', '数据线'),
    '宿舍生活': ('收纳盒', '台灯', '水杯', '置物架'),
    '运动闲置': ('跳绳', '瑜伽垫', '羽毛球拍', '护腕'),
}


def mask_phone(phone):
    phone = str(phone or '')
    return phone[:3] + '****' + phone[-4:] if len(phone) >= 11 else phone


def snapshot(m):
    now = time.time()
    since = now - 86400
    return {
        'pending_tickets': int(m.row("SELECT COUNT(*) n FROM tickets WHERE status='open'")['n']),
        'processing_tickets': int(m.row("SELECT COUNT(*) n FROM tickets WHERE status IN ('processing','review')")['n']),
        'users': int(m.row("SELECT COUNT(*) n FROM users WHERE status='active'")['n']),
        'active_24h': int(m.row("SELECT COUNT(DISTINCT user_id) n FROM sessions WHERE expires>?", (now,))['n']),
        'products': int(m.row("SELECT COUNT(*) n FROM products WHERE status='available'")['n']),
        'orders_24h': int(m.row("SELECT COUNT(*) n FROM orders WHERE created>=?", (since,))['n']),
        'audit_recent': [dict(r) for r in m.rows(
            'SELECT id,type,reason,created FROM audit ORDER BY id DESC LIMIT 5')],
    }


def format_stats(stats):
    return (f"待处理工单 {stats['pending_tickets']}，处理中 {stats['processing_tickets']}，"
            f"活跃用户 {stats['users']}（24h {stats['active_24h']}），"
            f"在售商品 {stats['products']}，24h 订单 {stats['orders_24h']}。")


def parse_action(question):
    q = str(question or '').strip()
    role_map = {'管理员': 'admin', '客服': 'support', '开发者': 'developer',
                '普通用户': 'user', '用户': 'user'}
    m = re.search(r'把\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?\s*(?:降为|设为|改成|调整为|转为)\s*(管理员|客服|开发者|普通用户|用户)', q)
    if m:
        return {'kind': 'role', 'name': m.group(1), 'role': role_map[m.group(2)]}
    m = re.search(r'(?:注销|停用|禁用|封禁)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?', q)
    if m:
        return {'kind': 'disable', 'name': m.group(1), 'role': None}
    m = re.search(r'(?:强制|踢)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?\s*(?:下线|退出)', q)
    if m:
        return {'kind': 'revoke', 'name': m.group(1), 'role': None}
    return None


def resolve_target(m, name):
    name = str(name or '').strip().strip('「」"“”')
    if not name:
        return None
    rows = m.rows("SELECT id,nickname,role,status FROM users WHERE nickname=? AND status='active'", (name,))
    if not rows:
        rows = m.rows("SELECT id,nickname,role,status FROM users WHERE nickname LIKE ? AND status='active'",
                      ('%' + name + '%',))
    if not rows:
        return None
    rows.sort(key=lambda r: ROLE_RANK.get(r['role'], -1), reverse=True)
    return rows[0]


def _ticket_answer(m, question):
    status = None
    label = '待处理'
    if '处理中' in question or '进行中' in question:
        status, label = 'processing', '处理中'
    elif '复核' in question:
        status, label = 'review', '待复核'
    elif '已解决' in question or '结案' in question:
        status, label = 'resolved', '已解决'
    sql = ("SELECT t.id,t.subject,t.body,t.status,t.created,u.nickname FROM tickets t "
           "JOIN users u ON u.id=t.user_id ")
    args = []
    if status:
        sql += 'WHERE t.status=? '
        args.append(status)
    else:
        sql += "WHERE t.status='open' "
    sql += 'ORDER BY t.id DESC LIMIT 6'
    rows = [dict(r) for r in m.rows(sql, tuple(args))]
    n = len(rows)
    if not rows:
        return {'answer': f'当前没有{label}工单。', 'items': [], 'office_tool': None, 'tickets': []}
    items = [{'title': f"#{r['id']} {r['subject']}", 'meta': f"{r['nickname']} · {r['status']}"} for r in rows]
    return {
        'answer': f'当前有 {n} 张{label}工单（最多显示 6 张）。需要处理建议可以点下方「查看明细与处理建议」。',
        'items': items,
        'office_tool': 'tickets',
        'tickets': rows,
    }


def _user_answer(m, question):
    # 先看有没有明确昵称：查/找/用户/账号 后面的一串字
    m2 = re.search(r'(?:查|找|搜索|看看)\s*[「"“]?([^」"”\s，。]{1,20})[」"”]?', question)
    if m2:
        rows = m.rows("SELECT id,nickname,role,status,phone,college FROM users WHERE nickname LIKE ? ORDER BY id LIMIT 8",
                      ('%' + m2.group(1) + '%',))
        if rows:
            items = [{'title': r['nickname'], 'meta': f"{ROLE_LABELS.get(r['role'], r['role'])} · {r['status']} · {mask_phone(r['phone'])}"}
                     for r in rows]
            return {'answer': f"找到 {len(rows)} 个匹配账号（手机号已打码）。", 'items': items}
    rows = m.rows("SELECT role,COUNT(*) n FROM users WHERE status='active' GROUP BY role ORDER BY role")
    parts = [f"{ROLE_LABELS.get(r['role'], r['role'])} {r['n']}" for r in rows]
    return {'answer': '当前活跃账号：' + '，'.join(parts) + '。',
            'items': [{'title': ROLE_LABELS.get(r['role'], r['role']), 'meta': f"{r['n']} 人"} for r in rows]}


def _product_answer(m):
    rows = m.rows("SELECT id,title,price,status,created FROM products WHERE status='available' ORDER BY id DESC LIMIT 6")
    total = int(m.row("SELECT COUNT(*) n FROM products WHERE status='available'")['n'])
    items = [{'title': r['title'], 'meta': f"¥{int(r['price']) / 100:.2f}"} for r in rows]
    return {'answer': f'当前在售商品 {total} 件（最多显示 6 件）。', 'items': items}


def _order_answer(m):
    since = time.time() - 86400
    rows = m.rows("SELECT id,status,total,created FROM orders WHERE created>=? ORDER BY id DESC LIMIT 6", (since,))
    total = int(m.row("SELECT COUNT(*) n FROM orders WHERE created>=?", (since,))['n'])
    items = [{'title': f"订单 #{r['id']}", 'meta': f"{r['status']} · ¥{int(r['total']) / 100:.2f}"} for r in rows]
    return {'answer': f'24 小时内新增订单 {total} 笔（最多显示 6 笔）。', 'items': items}


def _audit_answer(m):
    rows = m.rows('SELECT id,type,reason,created FROM audit ORDER BY id DESC LIMIT 8')
    items = [{'title': f"#{r['id']} {r['type']}", 'meta': str(r['reason'] or '')[:40]} for r in rows]
    return {'answer': '最近 8 条审计记录：', 'items': items}


def answer(m, question, mode='query'):
    q = str(question or '').strip()
    stats = snapshot(m)
    action = parse_action(q)
    if action:
        target = resolve_target(m, action['name'])
        if not target:
            return {'answer': f"没找到「{action['name']}」对应的运营账号。请说完整昵称，或到管理台操作。",
                    'proposal': None, 'mode': 'rule', 'stats': stats, 'items': []}
        if target['role'] == 'owner':
            return {'answer': '所有者账号不能通过助手调整，只能由运维在数据库处理。',
                    'proposal': None, 'mode': 'rule', 'stats': stats, 'items': []}
        if action['kind'] == 'role':
            summary = '把「%s」从%s调整为%s，并撤销其登录会话' % (
                target['nickname'], ROLE_LABELS.get(target['role'], target['role']),
                ROLE_LABELS.get(action['role'], action['role']))
        elif action['kind'] == 'disable':
            summary = '注销「%s」的账号，并撤销其所有登录会话' % target['nickname']
        else:
            summary = '强制「%s」下线（撤销其所有登录会话）' % target['nickname']
        return {'answer': '找到「%s」。这是不可逆操作，请再次确认：%s。' % (target['nickname'], summary),
                'proposal': {'kind': action['kind'], 'target': target['id'],
                             'nickname': target['nickname'], 'role': action.get('role'),
                             'summary': summary},
                'mode': 'rule', 'stats': stats, 'items': []}

    if mode == 'draft':
        text = (f"【{q or '平台公告'}】\n"
                f"当前平台数据：{format_stats(stats)}\n"
                f"请各位同学按平台规则交易，售后问题请提交工单，客服 08:00—20:00 处理。")
        return {'answer': text, 'proposal': None, 'mode': 'rule', 'stats': stats,
                'items': [], 'draft': True}

    if any(k in q for k in ('工单', '待处理', '处理中', '复核', '结案')):
        res = _ticket_answer(m, q)
    elif any(k in q for k in ('用户', '账号', '成员', '谁')):
        res = _user_answer(m, q)
    elif any(k in q for k in ('商品', '在售', '库存')):
        res = _product_answer(m)
    elif any(k in q for k in ('订单', '成交')):
        res = _order_answer(m)
    elif any(k in q for k in ('审计', '操作记录')):
        res = _audit_answer(m)
    else:
        res = {'answer': '平台数据快照：' + format_stats(stats), 'items': []}
    res.update({'proposal': None, 'mode': 'rule', 'stats': stats})
    return res


def photo_for(category, index=0):
    pool = PHOTOS.get(category) or PHOTOS['宿舍生活']
    return pool[index % len(pool)]


def _categories_for(prompt):
    """按主题关键词选分类，避免「宿舍好物」生成一堆教材。"""
    if any(k in prompt for k in ('书', '教材', '笔记', '习题')):
        return ['教材书籍']
    if any(k in prompt for k in ('电子', '充电', '耳机', '电脑', '手机', '键盘')):
        return ['电子产品']
    if any(k in prompt for k in ('运动', '健身', '球', '瑜伽', '跳绳', '跑步')):
        return ['运动闲置']
    if any(k in prompt for k in ('宿舍', '收纳', '台灯', '水杯', '置物', '寝室')):
        return ['宿舍生活']
    return list(CATEGORIES)


def generate(prompt, count=5):
    """规则生成演示商品预览：不调用模型，结果确定、可复现。"""
    prompt = str(prompt or '').strip()[:16] or '校园好物'
    try:
        count = max(1, min(int(count or 5), 10))
    except (TypeError, ValueError):
        count = 5
    cats = _categories_for(prompt)
    items = []
    for i in range(count):
        category = cats[i % len(cats)]
        suffix = PRODUCT_TEMPLATES[category][(i // len(cats)) % len(PRODUCT_TEMPLATES[category])]
        items.append({
            'title': f'{prompt}·{suffix}'[:40],
            'category': category,
            'price': (1200 + i * 700) * 1,
            'condition': CONDITIONS[i % len(CONDITIONS)],
            'description': f'{prompt}主题的演示商品，校园内公共区域面交，具体成色以实物为准。',
            'photo': photo_for(category, i),
        })
    return items


def clean_items(items):
    out = []
    for idx, row in enumerate(items if isinstance(items, list) else []):
        if not isinstance(row, dict):
            continue
        title = str(row.get('title') or '').strip()[:40]
        category = str(row.get('category') or '').strip()
        condition = str(row.get('condition') or '').strip()
        desc = str(row.get('description') or '').strip()[:200]
        try:
            price = int(row.get('price') or 0)
        except (TypeError, ValueError):
            continue
        if not title or category not in CATEGORIES:
            continue
        if condition not in CONDITIONS:
            condition = '正常使用痕迹'
        if price < 0 or price > 2000 * 100:
            continue
        out.append({'title': title, 'category': category, 'price': price,
                    'condition': condition, 'description': desc,
                    'photo': str(row.get('photo') or photo_for(category, idx))[:200]})
        if len(out) >= 10:
            break
    return out
