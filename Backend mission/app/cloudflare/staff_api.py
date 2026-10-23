"""Explicit atomic D1 adapters for support and administration."""
import csv
import datetime
import hashlib
import io
import json
import secrets
import time
from workers import Response
from .http import ApiError, int_param, json_body, json_response, path_of, query_of, require
from . import crypto
from ..account.credit import (VIOLATION_BASE, VIOLATION_LABEL, suggest_penalty, AWARD_REASON_PREFIX,
    AWARD_DAILY_CAP, AWARD_MONTHLY_CAP, day_start, month_start)

STAFF = ('support', 'admin', 'developer', 'owner')
# 角色层级：参照 GitLab 的 Guest < Reporter < Developer < Maintainer < Owner。
# Owner（L1）在开发者之上，可任免开发者及以下成员；所有者账号本身不允许通过
# 后台接口降级/停用（防止把最后一个 Owner 锁死），只能由运维在数据库设置。
RANK = {'user': 0, 'support': 1, 'admin': 2, 'developer': 3, 'owner': 4}
NAMES = {'user': '普通用户', 'support': '客服', 'admin': '平台管理员',
         'developer': '开发者', 'owner': '平台所有者'}

# 备份覆盖的应用表清单。schema.sql 每加一张表，这里就必须补上：
# cf_staff_backup 里 `found <= set(BACKUP_TABLES)` 会拦住缺表的备份（宁可 503，
# 也不能悄悄漏一张表交付），tests/test_cloudflare_staff.py 还会静态比对 schema.sql，
# 迁移加表忘了补清单时测试先红，不会等到线上点备份才发现。
BACKUP_TABLES = ['ai_office_jobs', 'ai_settings', 'ai_usage', 'audit', 'auth_attempts', 'blocks', 'comments',
                 'friendships', 'ledger', 'members', 'message_hides', 'messages', 'nominations',
                 'notifications', 'offers', 'order_changes', 'order_notes', 'orders', 'otp',
                 'password_credentials', 'posts', 'products', 'reactions', 'reviews', 'room_pins',
                 'rooms', 'sessions', 'settings', 'ticket_messages', 'tickets', 'uploads',
                 'user_avatar_uploads', 'users', 'wants']


def text(value, limit, label):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, label+'需填写且长度有效')
    return value.strip()


def ident(value):
    require(type(value) is int and value > 0, '编号无效')
    return value


class StaffApi:
    async def cf_staff_actor(self, request, admin=False):
        uid = await self.page_user(request, staff=True)
        role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        require(not admin or role in ('admin', 'developer', 'owner'), '仅平台管理员、开发者或所有者可操作', 403)
        return uid, role

    def cf_staff_audit(self, uid, kind, reason, target=None, tid=None, delta=None):
        return ('INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) VALUES(?,?,?,?,?,?,?)',
                (uid, target, kind, delta, reason, tid, time.time()))

    def cf_staff_notify(self, uid, kind, body, oid=None, tid=None):
        return ('INSERT INTO notifications(user_id,kind,body,order_id,ticket_id,created) VALUES(?,?,?,?,?,?)',
                (uid, kind, body, oid, tid, time.time()))

    async def cf_staff_commit(self, uid, guard, args, statements, roles=STAFF):
        # Authorization is rechecked in the mutation batch, not only before awaited reads.
        marks = ','.join('?' for _ in roles)
        sql = 'SELECT 1 WHERE EXISTS(SELECT 1 FROM users WHERE id=? AND status=\'active\' AND role IN ('+marks+')) AND EXISTS('+guard+')'
        return await self.db.guarded_batch(sql, (uid, *roles, *args), statements)

    async def cf_staff_ticket_dto(self, uid, tid):
        t = await self.db.first('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?', (tid,))
        require(t, '工单不存在', 404)
        role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        o = await self.db.first('SELECT * FROM orders WHERE id=?', (t['order_id'],)) if t['order_id'] else None
        require(role in STAFF or uid == t['user_id'] or (o and uid in (o['buyer_id'], o['seller_id'])), '不能查看他人工单', 403)
        t['messages'] = await self.db.all('SELECT m.*,u.nickname FROM ticket_messages m JOIN users u ON u.id=m.user_id WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY m.id', (tid, int(role in STAFF)))
        return t

    async def cf_staff_conflict(self, uid, t):
        require(uid != t['user_id'], '不能审核自己提交的工单', 403)
        if t.get('product_id'):
            p = await self.db.first('SELECT seller_id FROM products WHERE id=?', (t['product_id'],))
            require(not p or p['seller_id'] != uid, '不能审核自己发布商品的投诉', 403)
            for o in await self.db.all('SELECT items FROM orders WHERE buyer_id=? OR seller_id=?', (uid, uid)):
                require(not any(x.get('id') == t['product_id'] for x in json.loads(o['items'] or '[]')), '该商品交易与你存在利益冲突', 403)
        if t.get('order_id'):
            o = await self.db.first('SELECT buyer_id,seller_id FROM orders WHERE id=?', (t['order_id'],))
            require(not o or uid not in (o['buyer_id'], o['seller_id']), '不能审核自己的交易', 403)

    def cf_staff_ticket_guard(self, uid, t):
        sql = "SELECT 1 FROM tickets t WHERE t.id=? AND t.status=? AND t.user_id<>? AND t.order_id IS ? AND t.product_id IS ? AND NOT EXISTS(SELECT 1 FROM products p WHERE p.id=t.product_id AND p.seller_id=?) AND NOT EXISTS(SELECT 1 FROM orders x WHERE (x.buyer_id=? OR x.seller_id=?) AND (x.id=t.order_id OR EXISTS(SELECT 1 FROM json_each(x.items) j WHERE json_extract(j.value,'$.id')=t.product_id)))"
        return sql, (t['id'], t['status'], uid, t['order_id'], t['product_id'], uid, uid, uid)

    async def cf_staff_tickets(self, request):
        uid = await self.page_user(request)
        if request.method == 'GET':
            role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
            rows = await self.db.all('SELECT t.id FROM tickets t LEFT JOIN orders o ON o.id=t.order_id WHERE ?=1 OR t.user_id=? OR o.buyer_id=? OR o.seller_id=? ORDER BY t.id DESC', (int(role in STAFF), uid, uid, uid))
            return json_response([await self.cf_staff_ticket_dto(uid, r['id']) for r in rows])
        d = await json_body(request)
        typ = d.get('type', 'other'); require(typ in ('refund', 'report', 'appeal', 'reschedule', 'other'), '工单类型错误')
        subject = text(d.get('subject'), 80, '问题标题'); body = text(d.get('body'), 3000, '问题说明')
        oid = ident(d['order_id']) if d.get('order_id') else None
        pid = ident(d['product_id']) if d.get('product_id') else None
        if pid:
            require(await self.db.first('SELECT 1 FROM products WHERE id=?', (pid,)), '商品不存在', 404)
            if not oid and typ in ('report', 'appeal'):
                for r in await self.db.all('SELECT id,items FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC', (uid, uid)):
                    if any(x.get('id') == pid for x in json.loads(r['items'] or '[]')):
                        oid = r['id']; break
        o = await self.db.first('SELECT * FROM orders WHERE id=?', (oid,)) if oid else None
        if oid:
            require(o and uid in (o['buyer_id'], o['seller_id']), '不能关联他人订单', 403)
            require(not pid or any(x.get('id') == pid for x in json.loads(o['items'] or '[]')), '该订单不包含所选商品')
        require(typ != 'refund' or (o and uid == o['buyer_id'] and o['status'] in ('paid', 'awaiting_handover', 'awaiting_receipt', 'completed', 'disputed')), '订单当前不能申请退款')
        tid = secrets.randbits(48); now = time.time()
        stmts = [('INSERT INTO tickets(id,user_id,order_id,product_id,type,subject,body,created) VALUES(?,?,?,?,?,?,?,?)', (tid, uid, oid, pid, typ, subject, body, now))]
        guard = "SELECT 1 FROM users WHERE id=? AND status='active'"; args = (uid,)
        if o:
            guard += ' AND EXISTS(SELECT 1 FROM orders WHERE id=? AND status=? AND (buyer_id=? OR seller_id=?))'; args += (oid, o['status'], uid, uid)
        if typ == 'refund':
            guard += " AND NOT EXISTS(SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected'))"; args += (oid,)
            stmts.append(("UPDATE orders SET status='disputed' WHERE id=?", (oid,)))
        if o:
            other = o['seller_id'] if uid == o['buyer_id'] else o['buyer_id']
            stmts.append(self.cf_staff_notify(other, 'ticket_refund' if typ == 'refund' else 'ticket_filed', f'订单 #{oid} 已提交工单 #{tid}：{subject}', oid, tid))
        await self.db.guarded_batch(guard, args, stmts)
        return json_response(await self.cf_staff_ticket_dto(uid, tid))

    async def cf_staff_ticket(self, request):
        uid = await self.page_user(request)
        return json_response(await self.cf_staff_ticket_dto(uid, int_param(query_of(request), 'id')))

    async def cf_staff_reply_plan(self, uid, t, d):
        """准备现有工单回复的守卫、正文和通知，供工作台与办公助手原子提交。"""
        tid = t['id']; internal = bool(d.get('internal'))
        role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        require(not internal or role in STAFF, '没有客服权限', 403)
        stmts = [('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)', (tid, uid, text(d.get('body'), 2000, '回复'), int(internal), time.time()))]
        if not internal and role in STAFF:
            targets = {t['user_id']}
            if t['order_id']:
                o = await self.db.first('SELECT buyer_id,seller_id FROM orders WHERE id=?', (t['order_id'],))
                if o: targets.update((o['buyer_id'], o['seller_id']))
            stmts.extend(self.cf_staff_notify(x, 'ticket_reply', f'工单 #{tid} 客服已回复', t['order_id'], tid) for x in targets-{uid})
        roles = STAFF if internal or role in STAFF else ('user',)
        guard = 'SELECT 1 FROM tickets WHERE id=? AND order_id IS ?'; args = (tid, t['order_id'])
        if role not in STAFF:
            guard += ' AND (user_id=? OR EXISTS(SELECT 1 FROM orders WHERE id=tickets.order_id AND (buyer_id=? OR seller_id=?)))'; args += (uid, uid, uid)
        return guard, args, stmts, roles

    async def cf_staff_reply(self, request):
        """沿用原回复协议；与助手共用同一业务写入计划。"""
        uid = await self.page_user(request); d = await json_body(request); tid = ident(d.get('id'))
        t = await self.cf_staff_ticket_dto(uid, tid)
        guard, args, stmts, roles = await self.cf_staff_reply_plan(uid, t, d)
        await self.cf_staff_commit(uid, guard, args, stmts, roles)
        return json_response(await self.cf_staff_ticket_dto(uid, tid))

    async def cf_staff_resolve_plan(self, uid, t, d):
        """准备原有工单处理计划，保持退款、利益冲突、通知及会话归档规则。"""
        tid = t['id']; await self.cf_staff_conflict(uid, t)
        reason = text(d.get('reason'), 1000, '处理依据'); outcome = d.get('outcome', 'resolved')
        require(outcome in ('refund', 'reject', 'resolved', 'review', 'claim'), '处理方式无效')
        if t['status'] == 'resolved': return None
        o = await self.db.first('SELECT * FROM orders WHERE id=?', (t['order_id'],)) if t['order_id'] else None
        guard, args = self.cf_staff_ticket_guard(uid, t); stmts = []
        if outcome == 'refund':
            require(t['type'] == 'refund' and o and o['status'] == 'disputed', '只有争议退款工单可以退款')
            amount = d.get('amount', o['total']); require(type(amount) is int and 0 < amount <= o['total'], '退款不能超过订单金额')
            guard += " AND EXISTS(SELECT 1 FROM orders WHERE id=? AND status='disputed' AND total=? AND items=? AND buyer_id=? AND seller_id=?)"; args += (o['id'], o['total'], o['items'], o['buyer_id'], o['seller_id'])
            stmts.extend(await self.cf_trade_refund_statements(o, amount, time.time()))
        elif o and o['status'] == 'disputed' and t['type'] == 'refund' and outcome not in ('claim', 'review'):
            prior = 'completed' if o['completed_at'] else 'awaiting_receipt' if o['handover_at'] else 'awaiting_handover' if o['delivered_at'] else 'paid'
            guard += " AND EXISTS(SELECT 1 FROM orders WHERE id=? AND status='disputed' AND completed_at IS ? AND handover_at IS ? AND delivered_at IS ?)"; args += (o['id'], o['completed_at'], o['handover_at'], o['delivered_at'])
            stmts.append(('UPDATE orders SET status=? WHERE id=?', (prior, o['id'])))
        status = 'processing' if outcome == 'claim' else 'review' if outcome == 'review' else 'resolved'
        stmts.append(('UPDATE tickets SET status=?,assignee=?,outcome=?,reason=? WHERE id=?', (status, uid, outcome, reason, tid)))
        stmts.append(self.cf_staff_audit(uid, 'ticket_'+outcome, reason, tid=tid))
        if status == 'resolved':
            stmts.append(self.cf_staff_notify(t['user_id'], 'ticket_resolved', f'工单 #{tid} 已处理完成，可查看处理依据并申请复核', t['order_id'], tid))
            # 工单结案后，绑定的在线客服会话一并结束：事情有结论了，
            # 会话继续挂着只会让用户在已处理完的事项上反复追问。
            stmts.append(("UPDATE rooms SET support_status='closed',support_closed_at=?,support_closed_by='ticket',assignee=0 "
                          "WHERE support=1 AND ticket_id=? AND COALESCE(support_status,'open')='open'", (time.time(), tid)))
            stmts.append(("UPDATE messages SET removed=3 WHERE removed IN (0,1) AND room_id IN "
                          "(SELECT id FROM rooms WHERE support=1 AND ticket_id=? AND support_status='closed' AND support_closed_by='ticket')", (tid,)))
        return guard, args, stmts

    async def cf_staff_resolve(self, request):
        """工作台处理入口；办公助手复用计划，保持一个领域写入口。"""
        uid, _ = await self.cf_staff_actor(request); d = await json_body(request); tid = ident(d.get('id'))
        t = await self.cf_staff_ticket_dto(uid, tid)
        plan = await self.cf_staff_resolve_plan(uid, t, d)
        if plan:
            guard, args, stmts = plan
            await self.cf_staff_commit(uid, guard, args, stmts)
        return json_response({'ok': True})

    async def cf_staff_candidates(self, request):
        uid, _ = await self.cf_staff_actor(request)
        t = await self.cf_staff_ticket_dto(uid, int_param(query_of(request), 'id')); parties = {t['user_id']}; pid = t['product_id']
        if not pid and t['order_id']:
            o = await self.db.first('SELECT buyer_id,seller_id FROM orders WHERE id=?', (t['order_id'],))
            if o: parties.update((o['buyer_id'], o['seller_id']))
        out = []
        for r in await self.db.all('SELECT o.*,b.nickname buyer,s.nickname seller FROM orders o JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id ORDER BY o.id DESC'):
            items = json.loads(r['items'] or '[]'); matched = bool(pid and any(x.get('id') == pid for x in items))
            if (pid and not matched) or (not pid and not parties.intersection((r['buyer_id'], r['seller_id']))): continue
            out.append({**{k: r[k] for k in ('id', 'total', 'status', 'created', 'buyer', 'seller')}, 'titles': [x.get('title', '') for x in items], 'matched_product': matched})
            if len(out) >= 30: break
        return json_response(out)

    async def cf_staff_link(self, request):
        uid, _ = await self.cf_staff_actor(request); d = await json_body(request); tid = ident(d.get('id')); oid = ident(d.get('order_id'))
        t = await self.cf_staff_ticket_dto(uid, tid); o = await self.db.first('SELECT * FROM orders WHERE id=?', (oid,)); require(o, '订单不存在', 404)
        parties = {t['user_id']}
        if t['product_id']:
            p = await self.db.first('SELECT seller_id FROM products WHERE id=?', (t['product_id'],))
            if p: parties.add(p['seller_id'])
            require(any(x.get('id') == t['product_id'] for x in json.loads(o['items'] or '[]')), '该订单不包含工单涉及的商品')
        require(parties.intersection((o['buyer_id'], o['seller_id'])), '该订单与工单当事人无关，不能关联')
        require(t['type'] != 'refund' or t['order_id'] == oid, '退款工单不能改绑订单，请另建工单')
        await self.cf_staff_commit(uid, 'SELECT 1 FROM tickets WHERE id=? AND order_id IS ? AND product_id IS ?', (tid, t['order_id'], t['product_id']), [('UPDATE tickets SET order_id=? WHERE id=?', (oid, tid)), self.cf_staff_audit(uid, 'ticket_link_order', f'工单关联订单 #{oid}（原关联 {t["order_id"]}）', tid=tid)])
        return json_response(await self.cf_staff_ticket_dto(uid, tid))

    async def cf_staff_history(self, request):
        uid = await self.page_user(request)
        return json_response(await self.db.all("SELECT type kind,delta,reason,ticket_id,created FROM audit WHERE target=? AND type IN ('credit','stars') ORDER BY id DESC", (uid,)))

    async def cf_staff_credit(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True); d = await json_body(request)
        target = ident(d.get('target')); tid = ident(d.get('ticket_id')); require(uid != target, '不能处理自己的信誉')
        t = await self.cf_staff_ticket_dto(uid, tid); await self.cf_staff_conflict(uid, t)
        o = await self.db.first('SELECT * FROM orders WHERE id=?', (t['order_id'],)) if t['order_id'] else None
        violation = d.get('violation'); delta = d.get('delta')
        if violation:
            require(violation in VIOLATION_BASE, '违规类型无效'); amount = o['total'] if o else 0; suggested = suggest_penalty(violation, amount)
            if d.get('dry_run'): return json_response({'suggested': suggested, 'base': VIOLATION_BASE[violation], 'extra': suggested-VIOLATION_BASE[violation], 'amount': amount, 'label': VIOLATION_LABEL[violation]})
            if delta is None: delta = -suggested
        reason = text(d.get('reason'), 1000, '处罚/复核理由'); require(type(delta) is int and -100 <= delta <= 100 and delta != 0, '分值变动无效')
        require(t['status'] == 'resolved', '请先核实工单并记录处理结论')
        related = set()
        if o: related.update((o['buyer_id'], o['seller_id']))
        if t['product_id']:
            p = await self.db.first('SELECT seller_id FROM products WHERE id=?', (t['product_id'],))
            if p: related.add(p['seller_id'])
        if t['type'] == 'appeal' and delta > 0: related.add(t['user_id'])
        require(target in related, '工单与该用户无处罚或复核关联')
        guard, args = self.cf_staff_ticket_guard(uid, t)
        guard += " AND EXISTS(SELECT 1 FROM users WHERE id=?) AND NOT EXISTS(SELECT 1 FROM audit WHERE target=? AND ticket_id=? AND type='credit')"; args += (target, target, tid)
        await self.cf_staff_commit(uid, guard, args, [('UPDATE users SET score=MAX(0,MIN(100,score+?)) WHERE id=?', (delta, target)), self.cf_staff_audit(uid, 'credit', reason, target, tid, delta), self.cf_staff_notify(target, 'credit', f'你的信誉分有变动（{delta:+d} 分），可查看依据并申诉', tid=tid)], ('admin', 'developer'))
        return json_response(await self.profile_dto(target))

    async def cf_staff_accounts(self, request):
        uid, role = await self.cf_staff_actor(request, admin=True)
        if request.method == 'POST':
            d = await json_body(request); new_role = d.get('role') or 'support'
            require(new_role in ('support', 'admin', 'developer'), '角色无效'); require(role in ('developer', 'owner') or new_role == 'support', '只有开发者或所有者可以创建管理员/开发者账号', 403)
            phone = self.normalize_account(d.get('phone')); nickname = text(d.get('nickname'), 24, '昵称')
            salt, digest, rounds, recovery, recovery_digest = self.cf_staff_credentials(d)
            target = secrets.randbits(48)
            await self.cf_staff_commit(uid, 'SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM users WHERE phone=?)', (phone,), [('INSERT INTO users(id,phone,nickname,role) VALUES(?,?,?,?)', (target, phone, nickname, new_role)), ('INSERT INTO password_credentials VALUES(?,?,?,?,?)', (target, salt, digest, rounds, recovery_digest)), self.cf_staff_audit(uid, 'staff_create', f'创建{NAMES[new_role]}账号「{nickname}」', target)], ('developer',) if new_role != 'support' else ('admin', 'developer'))
            return json_response({'id': target, 'phone': phone, 'role': new_role, 'recovery_code': recovery})
        all_accounts = path_of(request).endswith('/accounts'); q = str(query_of(request).get('q') or '').strip(); kw = '%'+q+'%'
        where = "(?='' OR u.nickname LIKE ? OR u.phone LIKE ?)" if all_accounts else "u.role IN ('support','admin','developer','owner')"
        args = (time.time(), q, kw, kw) if all_accounts else (time.time(),)
        rows = await self.db.all('SELECT u.id,u.phone,u.nickname,u.college,u.score,u.role,u.status,u.last_login,(SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id AND s.expires>?) sessions FROM users u WHERE '+where+' ORDER BY u.id DESC LIMIT 300', args)
        for r in rows: r.update(role_name=NAMES[r['role']], online=bool(r['sessions']))
        return json_response(rows)

    def cf_staff_credentials(self, d):
        salt = self.check_salt(d.get('salt')); digest = self.check_digest(d.get('digest')); rounds = self.check_rounds(d.get('rounds'))
        require(rounds == crypto.ROUNDS, '运营账号必须使用当前完整口令派生轮数')
        recovery = secrets.token_urlsafe(32)
        return salt, digest, rounds, recovery, hashlib.sha256(recovery.encode()).hexdigest()

    async def cf_staff_account_action(self, request):
        uid, actor_role = await self.cf_staff_actor(request); d = await json_body(request)
        target = ident(d.get('target') if path_of(request).endswith('/role') else d.get('id')); require(target != uid, '不能对自己的账号执行此操作', 403)
        t = await self.db.first('SELECT * FROM users WHERE id=?', (target,)); require(t, '账号不存在', 404)
        require(t['role'] != 'owner', '所有者账号只能由运维在数据库调整', 403)
        action = path_of(request).rsplit('/', 1)[-1]; stmts = []; response = {'ok': True}; guard = 'SELECT 1 FROM users WHERE id=? AND role=? AND status=?'; args = (target, t['role'], t['status']); roles = STAFF
        if action == 'revoke':
            require(t['role'] not in STAFF or actor_role in ('admin', 'developer', 'owner'), '只有管理员可以强制下线运营账号', 403)
            if t['role'] in STAFF: roles = ('admin', 'developer', 'owner')
            response = {'revoked': await self.db.scalar('SELECT COUNT(*) FROM sessions WHERE user_id=?', (target,))}; kind = 'session_revoke'
        else:
            require(actor_role in ('admin', 'developer', 'owner'), '仅平台管理员、开发者或所有者可操作', 403); roles = (actor_role,)
            if action == 'role':
                nr = d.get('role'); require(nr in RANK, '未知角色')
                require(nr != 'owner', '所有者角色只能由运维设置', 403)
                require(actor_role in ('developer', 'owner') or (nr in ('user', 'support') and RANK[t['role']] < 2), '不能调整同级或更高等级账号', 403)
                if t['role'] == 'developer' and nr != 'developer': guard += " AND (SELECT COUNT(*) FROM users WHERE role='developer' AND status='active')>1"
                stmts.append(('UPDATE users SET role=? WHERE id=?', (nr, target))); kind = 'role_change'
            else:
                require(t['role'] in STAFF, '这里只管理客服与管理员账号')
                require(actor_role in ('developer', 'owner') or RANK[t['role']] < RANK[actor_role], '不能操作同级或更高等级运营账号', 403)
                if action == 'status':
                    status = d.get('status'); require(status in ('active', 'disabled'), '状态无效')
                    require(t['status'] in ('active', 'disabled'), '不能恢复封禁或注销账号')
                    if t['role'] == 'developer' and status == 'disabled': guard += " AND (SELECT COUNT(*) FROM users WHERE role='developer' AND status='active')>1"
                    stmts.append(('UPDATE users SET status=? WHERE id=?', (status, target))); kind = 'staff_'+('enable' if status == 'active' else 'disable')
                else:
                    salt, digest, rounds, recovery, rd = self.cf_staff_credentials(d)
                    guard += ' AND EXISTS(SELECT 1 FROM password_credentials WHERE user_id=?)'; args += (target,)
                    stmts.extend([('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?', (salt, digest, rounds, rd, target)), ('DELETE FROM auth_attempts WHERE phone=?', (t['phone'],))]); kind = 'staff_password_reset'; response = {'recovery_code': recovery}
        if action != 'status' or d.get('status') == 'disabled': stmts.append(('DELETE FROM sessions WHERE user_id=?', (target,)))
        stmts.append(self.cf_staff_audit(uid, kind, f'{kind}「{t["nickname"]}」', target))
        await self.cf_staff_commit(uid, guard, args, stmts, roles)
        return json_response(await self.profile_dto(target) if action == 'status' else response)

    async def cf_staff_review(self, request):
        uid = await self.page_user(request); d = await json_body(request); oid = ident(d.get('order_id'))
        rating = d.get('rating'); require(type(rating) is int and 1 <= rating <= 5, '评分需1至5分')
        body = text(d.get('body'), 500, '评价'); o = await self.db.first('SELECT * FROM orders WHERE id=?', (oid,))
        require(o and o['status'] == 'completed' and uid in (o['buyer_id'], o['seller_id']), '完成真实有效订单后才能评价')
        ratee = o['seller_id'] if uid == o['buyer_id'] else o['buyer_id']; now = time.time(); aid = secrets.randbits(48)
        stmts = []
        if rating >= 4:
            reason = f'{AWARD_REASON_PREFIX}（订单 #{oid} · {rating} 星）'
            # Evaluate the old review and caps inside this batch before replacing the review.
            stmts.append(("INSERT INTO audit(id,actor,target,type,delta,reason,created) SELECT ?,0,?,'credit',1,?,? WHERE NOT EXISTS(SELECT 1 FROM reviews WHERE order_id=? AND user_id=? AND rating>=4) AND (SELECT COUNT(*) FROM audit WHERE target=? AND type='credit' AND delta>0 AND reason LIKE ? AND created>=?)<? AND (SELECT COUNT(*) FROM audit WHERE target=? AND type='credit' AND delta>0 AND reason LIKE ? AND created>=?)<?", (aid, ratee, reason, now, oid, uid, ratee, AWARD_REASON_PREFIX+'%', day_start(now), AWARD_DAILY_CAP, ratee, AWARD_REASON_PREFIX+'%', month_start(now), AWARD_MONTHLY_CAP)))
            stmts.append(('UPDATE users SET score=MIN(100,score+1) WHERE id=? AND EXISTS(SELECT 1 FROM audit WHERE id=?)', (ratee, aid)))
            stmts.append(("INSERT INTO notifications(user_id,kind,body,created) SELECT ?,'credit',?,? WHERE EXISTS(SELECT 1 FROM audit WHERE id=?)", (ratee, f'你因订单 #{oid} 获得好评，信誉分 +1。', now, aid)))
        stmts.append(('INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?) ON CONFLICT(order_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body', (oid, uid, rating, body, now)))
        await self.db.guarded_batch("SELECT 1 FROM orders o JOIN users u ON u.id=? WHERE o.id=? AND o.status='completed' AND o.buyer_id=? AND o.seller_id=? AND u.status='active'", (uid, oid, o['buyer_id'], o['seller_id']), stmts)
        return json_response({'ok': True, 'simulation': True})

    async def cf_staff_dossier(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True); target = int_param(query_of(request), 'id')
        user = await self.profile_dto(target)
        await self.cf_staff_commit(uid, 'SELECT 1 FROM users WHERE id=?', (target,), [self.cf_staff_audit(uid, 'dossier_view', '查阅用户档案', target)], ('admin', 'developer'))
        from ..support.service import SupportService
        # Masking is a pure helper; never include password credentials or chat bodies.
        phone = await self.db.scalar('SELECT phone FROM users WHERE id=?', (target,))
        orders = await self.db.all('SELECT id,buyer_id,seller_id,status,total,created FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT 50', (target, target))
        for o in orders: o['role'] = 'buyer' if o['buyer_id'] == target else 'seller'
        products = [await self.listing_dto(r) for r in await self.db.all('SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p JOIN users u ON u.id=p.seller_id WHERE p.seller_id=? ORDER BY p.id DESC', (target,))]
        payload = {'user': user, 'phone': SupportService.mask_phone(phone), 'orders': orders, 'products': products, 'served_by': uid}
        for name, sql in {
            'tickets': 'SELECT id,type,subject,status,order_id,product_id,created FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 50',
            'comments': 'SELECT c.id,c.post_id,c.body,c.created,p.topic FROM comments c JOIN posts p ON p.id=c.post_id WHERE c.user_id=? ORDER BY c.id DESC LIMIT 50',
            'posts': 'SELECT id,topic,body,created,removed FROM posts WHERE user_id=? ORDER BY id DESC LIMIT 50',
            'reviews': 'SELECT id,order_id,rating,body,created FROM reviews WHERE user_id=? ORDER BY id DESC LIMIT 50',
            'wants': 'SELECT id,keyword,budget,status,created FROM wants WHERE user_id=? ORDER BY id DESC LIMIT 50',
            'audit': 'SELECT id,actor,target,type,delta,reason,ticket_id,created FROM audit WHERE target=? ORDER BY id DESC LIMIT 100',
        }.items(): payload[name] = await self.db.all(sql, (target,))
        return json_response(payload)

    async def cf_admin_chats(self, request):
        """管理端：某人的会话清单（最后一条摘要）。仅 admin/developer。"""
        await self.cf_staff_actor(request, admin=True); target = int_param(query_of(request), 'user_id')
        rooms = await self.db.all('''SELECT r.id,r.kind,r.name,r.college,r.support,r.ticket_id,
                m.role member_role,m.muted,
                (SELECT COUNT(*) FROM messages x WHERE x.room_id=r.id) message_count,
                (SELECT MAX(x.id) FROM messages x WHERE x.room_id=r.id) last_id
            FROM members m JOIN rooms r ON r.id=m.room_id
            WHERE m.user_id=? ORDER BY COALESCE(last_id,0) DESC, r.id DESC''', (target,))
        for r in rooms:
            r['ticket_id'] = r.get('ticket_id') or 0
            r['last'] = await self.db.first('''SELECT x.id,x.user_id,x.removed,x.created,
                    CASE WHEN x.removed=1 THEN '消息已被移除' WHEN x.removed=2 THEN '' ELSE x.body END body,
                    un.nickname FROM messages x JOIN users un ON un.id=x.user_id
                WHERE x.room_id=? ORDER BY x.id DESC LIMIT 1''', (r['id'],))
            if r['kind'] == 'private':
                peer = await self.db.first('''SELECT us.id,us.nickname FROM members mm JOIN users us ON us.id=mm.user_id
                    WHERE mm.room_id=? AND mm.user_id<>? LIMIT 1''', (r['id'], target))
                r['peer'] = peer
                if peer: r['name'] = peer['nickname']
        return json_response({'user_id': target, 'rooms': rooms})

    async def cf_admin_chat(self, request):
        """管理端：只读读取某人在指定会话里的最近 200 条消息（写 chat_view 审计）。"""
        uid, _ = await self.cf_staff_actor(request, admin=True); q = query_of(request)
        target = int_param(q, 'user_id'); room_id = int_param(q, 'room_id')
        room = await self.db.first('SELECT * FROM rooms WHERE id=?', (room_id,)); require(room, '会话不存在', 404)
        require(await self.db.first('SELECT 1 FROM members WHERE room_id=? AND user_id=?', (room_id, target)), '该用户不在此会话中', 404)
        rows = await self.db.all('''SELECT x.id,x.room_id,x.user_id,x.removed,
                CASE WHEN x.removed=1 THEN '消息已被移除' WHEN x.removed=2 THEN '' ELSE x.body END body,
                x.created,un.nickname FROM messages x JOIN users un ON un.id=x.user_id
                WHERE x.room_id=? ORDER BY x.id DESC LIMIT 200''', (room_id,))
        rows.reverse()
        await self.cf_staff_commit(uid, 'SELECT 1 FROM members WHERE room_id=? AND user_id=?', (room_id, target),
                                   [self.cf_staff_audit(uid, 'chat_view', f'查阅聊天记录 · 会话#{room_id}', target)], ('admin', 'developer'))
        return json_response({'room': room, 'messages': rows})

    async def cf_staff_sellers(self, request):
        await self.cf_staff_actor(request)
        return json_response(await self.db.all("SELECT p.seller_id id,u.nickname,u.score,u.status user_status,SUM(CASE WHEN p.status='available' THEN 1 ELSE 0 END) available,SUM(CASE WHEN p.status='removed' THEN 1 ELSE 0 END) removed,COUNT(*) total FROM products p JOIN users u ON u.id=p.seller_id GROUP BY p.seller_id ORDER BY available DESC,total DESC LIMIT 200"))

    async def cf_staff_delist(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True); d = await json_body(request)
        target = ident(d.get('seller_id')); require(target != uid, '不能处置自己发布的商品'); reason = text(d.get('reason'), 500, '处置理由')
        seller = await self.db.first('SELECT id FROM users WHERE id=?', (target,)); require(seller, '卖家不存在', 404)
        rows = await self.db.all("SELECT id FROM products WHERE seller_id=? AND status='available' ORDER BY id", (target,)); require(rows, '该卖家当前没有在售商品可下架')
        ids = [r['id'] for r in rows]; encoded = json.dumps(ids)
        # Guard the complete set of available products; no partial shop action after concurrent listing/order.
        guard = "SELECT 1 WHERE (SELECT COUNT(*) FROM products WHERE seller_id=? AND status='available')=? AND NOT EXISTS(SELECT 1 FROM json_each(?) j LEFT JOIN products p ON p.id=j.value WHERE p.id IS NULL OR p.seller_id<>? OR p.status<>'available')"
        await self.cf_staff_commit(uid, guard, (target, len(ids), encoded, target), [("UPDATE products SET status='removed',delisted_by=?,promoted_until=0 WHERE seller_id=? AND status='available'", (uid, target)), self.cf_staff_audit(uid, 'seller_moderate', f'整店下架 {len(ids)} 件：{reason}', target), self.cf_staff_notify(target, 'product_moderate', f'你在售的 {len(ids)} 件商品已被平台下架。理由：{reason}。如有异议可申诉。')], ('admin', 'developer'))
        return json_response({'id': target, 'count': len(ids), 'ids': ids})

    async def cf_staff_content(self, request):
        uid, _ = await self.cf_staff_actor(request); d = await json_body(request)
        kind = d.get('kind'); require(kind in ('message', 'post'), '内容类型无效'); action = d.get('action', 'remove'); require(action in ('remove', 'restore'), '操作无效')
        reason = text(d.get('reason'), 500, '处置理由'); cid = ident(d.get('id')); table = 'messages' if kind == 'message' else 'posts'
        row = await self.db.first(f'SELECT user_id,removed FROM {table} WHERE id=?', (cid,)); require(row, '内容不存在', 404)
        require(row['user_id'] != uid, '不能处置自己发布的内容'); label = '聊天消息' if kind == 'message' else '社区帖子'
        stmts = [(f'UPDATE {table} SET removed=? WHERE id=?', (int(action == 'remove'), cid)), self.cf_staff_audit(uid, 'content_'+action, f'{label} #{cid}：{reason}', row['user_id'])]
        if action == 'remove': stmts.append(self.cf_staff_notify(row['user_id'], 'content_removed', f'你发布的一条{label}因「{reason}」已被移除。如有异议可申诉。'))
        await self.cf_staff_commit(uid, f'SELECT 1 FROM {table} WHERE id=? AND user_id=? AND removed=?', (cid, row['user_id'], row['removed']), stmts)
        return json_response({'ok': True})

    async def cf_staff_words(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True)
        from .builtin_words import BUILTIN_WORDS
        if request.method == 'GET':
            rules = await self.cf_rules(); custom = {w['word'] for w in rules.custom}
            return json_response({'total': len(rules), 'words': [{**w, 'custom': w['word'] in custom} for w in rules.words], 'custom_count': len(custom), 'disabled': sorted(rules.disabled), 'builtin_count': len(BUILTIN_WORDS), 'skipped': [{'source': s, 'word': w, 'reason': r} for s, w, r in rules.skipped]})
        d = await json_body(request); word = text(d.get('word'), 40, '词条'); op = d.get('op')
        old = await self.db.scalar("SELECT value FROM settings WHERE key='cloud_moderation_rules'")
        state = json.loads(old) if old else {'custom': [], 'disabled': []}; custom = state['custom']; disabled = set(state['disabled']); builtin = {w['word'] for w in BUILTIN_WORDS}
        if op == 'add':
            require(len(word) >= 2, '词条至少 2 个字符'); action = d.get('action') or 'block'; require(action in ('block', 'review', 'report'), '处置方式无效')
            custom = [w for w in custom if w['word'] != word]
            custom.append({'word': word, 'category': str(d.get('category') or '').strip()[:20] or '运营自定义', 'level': {'block': '高', 'review': '中', 'report': '低'}[action], 'action': action, 'source': 'custom'})
            disabled.discard(word)
        elif op == 'remove':
            require(word in builtin or any(w['word'] == word for w in custom), '词条不存在', 404)
            if word in builtin: disabled.add(word)
            else: custom = [w for w in custom if w['word'] != word]; disabled.discard(word)
        elif op == 'restore':
            require(word in disabled, '该词条没有处于停用状态', 404); disabled.remove(word)
        else: raise ApiError('不支持的操作')
        value = json.dumps({'custom': custom, 'disabled': sorted(disabled)}, ensure_ascii=False)
        await self.cf_staff_commit(uid, "SELECT 1 WHERE (SELECT value FROM settings WHERE key='cloud_moderation_rules') IS ?", (old,), [("INSERT INTO settings(key,value) VALUES('cloud_moderation_rules',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,)), self.cf_staff_audit(uid, 'wordlist_'+op, f'{op}词条「{word}」', uid)], ('admin', 'developer'))
        self._request_rules = None
        return json_response({'ok': True, 'word': word, **({'action': action} if op == 'add' else {})})

    async def cf_staff_nominate(self, request):
        uid, role = await self.cf_staff_actor(request, admin=True); require(role == 'admin', '仅平台管理员可任命', 403)
        d = await json_body(request); nid = ident(d.get('id'))
        n = await self.db.first("SELECT * FROM nominations WHERE id=? AND status='pending'", (nid,)); require(n, '申请不存在或已处理')
        await self.cf_staff_commit(uid, "SELECT 1 FROM nominations WHERE id=? AND status='pending' AND user_id=? AND room_id=? AND EXISTS(SELECT 1 FROM members WHERE user_id=? AND room_id=?)", (nid, n['user_id'], n['room_id'], n['user_id'], n['room_id']), [("UPDATE nominations SET status='approved' WHERE id=?", (nid,)), ("UPDATE members SET role='moderator' WHERE room_id=? AND user_id=?", (n['room_id'], n['user_id'])), self.cf_staff_audit(uid, 'appointment', '群管理员申请审核通过', n['user_id'])], ('admin',))
        return json_response({'ok': True})

    async def cf_staff_stars(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True); d = await json_body(request); target = ident(d.get('target')); delta = d.get('delta')
        require(uid != target, '不能调整自己的星级'); require(type(delta) is int and delta in (-2, -1, 1, 2), '星级调整需为 -2、-1、+1 或 +2')
        reason = text(d.get('reason'), 500, '调整理由'); t = await self.db.first('SELECT role,score FROM users WHERE id=?', (target,)); require(t, '用户不存在', 404); require(t['role'] not in ('admin', 'developer'), '不能调整管理员或开发者的星级', 403)
        badge = await self.star_badge(target, t['score']); applied = max(1, min(7, badge['stars']+delta))-badge['stars']; require(applied, '当前星级已达边界')
        guard = "SELECT 1 FROM users WHERE id=? AND role=? AND score=? AND (SELECT COUNT(*) FROM reviews r JOIN orders o ON o.id=r.order_id WHERE o.seller_id=? AND r.user_id=o.buyer_id AND r.rating>=4)=? AND (SELECT COUNT(*) FROM audit WHERE target=? AND type='credit' AND delta<=-15)=? AND (SELECT COALESCE(SUM(delta),0) FROM audit WHERE target=? AND type='stars')=?"
        await self.cf_staff_commit(uid, guard, (target, t['role'], t['score'], target, badge['good_reviews'], target, badge['severe_violations'], target, badge['stars_adjust']), [self.cf_staff_audit(uid, 'stars', reason, target, delta=applied), self.cf_staff_notify(target, 'credit', f'管理员将你的信誉星级调整 {applied:+d} 星：{reason}')], ('admin', 'developer'))
        return json_response(await self.star_badge(target, t['score']))

    def cf_staff_ban_order_statements(self, target, now):
        # Set-based mutations inspect live order state in the same D1 batch.
        closing = "(o.buyer_id=? OR o.seller_id=?) AND o.status='awaiting_payment' OR o.buyer_id=? AND o.status IN ('paid','awaiting_handover')"
        parties = (target, target, target)
        return [
            ("UPDATE products SET status=CASE WHEN seller_id<>? AND delisted_by=0 AND EXISTS(SELECT 1 FROM users u WHERE u.id=products.seller_id AND u.status='active' AND u.score>=60) THEN 'available' ELSE 'removed' END,promoted_until=0 WHERE status='reserved' AND id IN(SELECT json_extract(j.value,'$.id') FROM orders o,json_each(o.items) j WHERE "+closing+')', (target, *parties)),
            ("UPDATE wants SET status='open' WHERE status='matched' AND id IN(SELECT o.want_id FROM orders o WHERE "+closing+')', parties),
            ("INSERT INTO ledger(order_id,kind,amount,created) SELECT o.id,'service_fee_reversal',l.amount,? FROM orders o JOIN ledger l ON l.order_id=o.id AND l.kind='service_fee' WHERE ("+closing+") AND NOT EXISTS(SELECT 1 FROM ledger r WHERE r.order_id=o.id AND r.kind='service_fee_reversal')", (now, *parties)),
            ("INSERT INTO ledger(order_id,kind,amount,created) SELECT id,'refund',total,? FROM orders WHERE buyer_id=? AND status IN ('paid','awaiting_handover') AND NOT EXISTS(SELECT 1 FROM ledger l WHERE l.order_id=orders.id AND l.kind='refund')", (now, target)),
            ("INSERT INTO notifications(user_id,kind,order_id,body,created) SELECT CASE WHEN o.buyer_id=? THEN o.seller_id ELSE o.buyer_id END,'order_cancelled',o.id,'订单 #'||o.id||' 因账号被处置已关闭，请查看订单记录。',? FROM orders o WHERE "+closing, (target, now, *parties)),
            ("UPDATE orders AS o SET status='cancelled' WHERE "+closing, parties),
            ("INSERT INTO tickets(user_id,order_id,type,subject,body,status,created) SELECT buyer_id,id,'refund','卖家账号被处置，订单 #'||id||' 待退款','卖家账号已被平台处置，系统转争议，等待客服核实退款。','open',? FROM orders o WHERE seller_id=? AND status IN ('paid','awaiting_handover','awaiting_receipt') AND NOT EXISTS(SELECT 1 FROM tickets t WHERE t.order_id=o.id AND t.type='refund' AND t.status NOT IN ('resolved','rejected'))", (now, target)),
            ("INSERT INTO notifications(user_id,kind,order_id,ticket_id,body,created) SELECT buyer_id,'ticket_refund',id,(SELECT id FROM tickets t WHERE t.order_id=o.id AND t.type='refund' AND t.status NOT IN ('resolved','rejected') ORDER BY id DESC LIMIT 1),'订单 #'||id||' 卖家账号已被处置，已转入争议处理，客服将核实退款。',? FROM orders o WHERE seller_id=? AND status IN ('paid','awaiting_handover','awaiting_receipt')", (now, target)),
            ("UPDATE orders SET status='disputed' WHERE seller_id=? AND status IN ('paid','awaiting_handover','awaiting_receipt')", (target,)),
        ]

    async def cf_staff_ban(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True); d = await json_body(request); target = ident(d.get('target'))
        require(uid != target, '不能封禁自己'); banned = d.get('banned', True); require(type(banned) is bool, '封禁状态无效'); reason = text(d.get('reason'), 500, '封禁/解封理由')
        t = await self.db.first('SELECT role,status FROM users WHERE id=?', (target,)); require(t, '用户不存在', 404); require(t['role'] not in ('admin', 'developer'), '不能封禁管理员或开发者', 403)
        require(banned or t['status'] == 'banned', '该账号当前不是封禁状态，无法解封'); require(not banned or t['status'] in ('active', 'banned', 'disabled'), '不能封禁已注销或清除账号')
        stmts = self.cf_staff_ban_order_statements(target, time.time()) if banned else []
        stmts.append(('UPDATE users SET status=? WHERE id=?', ('banned' if banned else 'active', target)))
        if banned:
            stmts.extend([('DELETE FROM sessions WHERE user_id=?', (target,)), ("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target,))])
        stmts.append(self.cf_staff_audit(uid, 'ban' if banned else 'unban', reason, target))
        await self.cf_staff_commit(uid, 'SELECT 1 FROM users WHERE id=? AND role=? AND status=?', (target, t['role'], t['status']), stmts, ('admin', 'developer'))
        return json_response(await self.profile_dto(target))

    async def cf_staff_purge(self, request):
        # 分级：开发者可清管理员/客服/用户；管理员可清客服/用户；同级或更高不可清。
        uid, role = await self.cf_staff_actor(request, admin=True)
        d = await json_body(request); target = ident(d.get('target')); require(target != uid, '不能清除自己的账号'); text(d.get('reason'), 500, '清除理由')
        t = await self.db.first('SELECT role FROM users WHERE id=?', (target,)); require(t, '用户不存在', 404)
        require(RANK.get(role, -1) > RANK.get(t['role'], 99), '不能清除同级或更高等级的账号', 403)
        now = time.time()
        account = await self.db.first('SELECT phone,status FROM users WHERE id=?', (target,))
        # 没参与过订单的账号不需要跑整套订单结算（其中用到 json_each）。
        # 本地测试环境的 sqlite 没编 JSON1，跳过也避免误报；线上 D1 支持。
        has_orders = await self.db.scalar('SELECT COUNT(*) FROM orders WHERE buyer_id=? OR seller_id=?', (target, target))
        statements = self.cf_staff_ban_order_statements(target, now) if has_orders else []
        statements.extend([
            ("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target,)),
            ('DELETE FROM sessions WHERE user_id=?', (target,)),
            ('DELETE FROM password_credentials WHERE user_id=?', (target,)),
            ('DELETE FROM auth_attempts WHERE phone=?', (account['phone'],)),
            ("UPDATE users SET phone=?,nickname=?,status='deleted',bio='',avatar_upload_id=NULL WHERE id=?", (f'deleted+{target}@{int(now)}.local', f'已注销用户#{target}', target)),
            self.cf_staff_audit(uid, 'account_purge', d['reason'].strip(), target),
        ])
        await self.cf_staff_commit(uid, 'SELECT 1 FROM users WHERE id=? AND role=? AND status=? AND phone=?', (target, t['role'], account['status'], account['phone']), statements, ('admin', 'developer'))
        from ..support.service import SupportService
        return json_response({'ok': True, 'freed_phone': SupportService.mask_phone(account['phone'])})

    async def cf_staff_export(self, request):
        uid, _ = await self.cf_staff_actor(request); query = query_of(request); query['limit'] = '1000'
        rows = await self.audit_rows(uid, query); stream = io.StringIO(newline=''); writer = csv.writer(stream)
        writer.writerow(['编号', '时间', '操作人', '操作人昵称', '类型', '对象用户', '分值', '理由', '工单'])
        def safe(value):
            if type(value) in (int, float): return value
            value = '' if value is None else str(value)
            return "'"+value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
        for r in rows:
            r = dict(r)
            r['created'] = datetime.datetime.fromtimestamp(r['created']).strftime('%Y-%m-%d %H:%M:%S') if r['created'] else ''
            writer.writerow([safe(r.get(k)) for k in ('id', 'created', 'actor', 'actor_name', 'type', 'target', 'delta', 'reason', 'ticket_id')])
        return Response(('\ufeff'+stream.getvalue()).encode('utf-8'), headers={'Content-Type': 'text/csv; charset=utf-8', 'Cache-Control': 'private, no-store', 'Content-Disposition': 'attachment; filename="audit.csv"', 'X-Content-Type-Options': 'nosniff'})

    async def cf_staff_backup(self, request):
        uid, _ = await self.cf_staff_actor(request, admin=True)
        import zipfile
        # Only project tables, all read inside one D1 batch snapshot. Hard bounds fail explicitly.
        tables = BACKUP_TABLES
        results = await self.db.batch([("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index') AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'", ())]+[(f'SELECT * FROM "{table}" LIMIT 10001', ()) for table in tables])
        schema = [dict(r) for r in results[0].results]; snapshot = {table: [dict(r) for r in result.results] for table, result in zip(tables, results[1:])}
        require(all(len(rows) <= 10000 for rows in snapshot.values()), '数据量超出在线备份上限，请使用 Cloudflare D1/R2 导出工具', 413)
        # Refuse silently incomplete backups if a schema migration added another application table.
        found = {r['name'] for r in schema if r['sql'].lstrip().upper().startswith('CREATE TABLE') and not r['name'].startswith(('_cf_', 'd1_', 'sqlite_'))}
        require(found <= set(tables), '备份表清单需随数据库迁移更新', 503)
        def sql_value(value):
            if value is None: return 'NULL'
            if type(value) in (int, float): return str(value)
            if isinstance(value, bytes): return "X'"+value.hex()+"'"
            return "'"+str(value).replace("'", "''")+"'"
        lines = ['PRAGMA foreign_keys=OFF;']+[r['sql']+';' for r in schema if r['name'] in tables and r['sql'].lstrip().upper().startswith('CREATE TABLE')]
        for table, rows in snapshot.items():
            for row in rows:
                cols = ','.join('"'+k.replace('"', '""')+'"' for k in row)
                lines.append(f'INSERT INTO "{table}"({cols}) VALUES('+','.join(sql_value(v) for v in row.values())+');')
        lines.extend(r['sql']+';' for r in schema if r['sql'].lstrip().upper().startswith('CREATE INDEX'))
        sql = '\n'.join(lines).encode('utf-8'); require(len(sql) <= 16*1024*1024, '数据库超过在线备份上限，请用 Cloudflare 导出工具', 413)
        media = sorted({r['path'] for table in ('uploads', 'user_avatar_uploads') for r in snapshot[table]})
        buffer = io.BytesIO(); checksums = {}; total = len(sql)
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('database.sql', sql); checksums['database.sql'] = hashlib.sha256(sql).hexdigest()
            for key in media:
                require(isinstance(key, str) and key.startswith('media/') and '..' not in key.split('/'), '媒体键不合法，备份中止', 503)
                payload, _ = await self.media_store.read(key); total += len(payload)
                require(total <= 32*1024*1024, '媒体超过在线备份上限，请用 Cloudflare R2 导出工具', 413)
                archive.writestr('r2/'+key, payload); checksums['r2/'+key] = hashlib.sha256(payload).hexdigest()
            archive.writestr('manifest.json', json.dumps({'format': 'huali-d1-r2-v1', 'created': time.time(), 'tables': tables, 'media': media, 'sha256': checksums, 'simulation': True}, ensure_ascii=False))
            archive.writestr('RESTORE.txt', 'Keep this archive private: it contains account credentials and private media.\nStop writes before restoring. Import database.sql into an EMPTY D1 database. Upload every file under r2/ to a PRIVATE R2 bucket using the same relative object key (media/...). Bind DB and MEDIA to that restored database/bucket. Verify manifest SHA-256 checksums before restore and reconcile orders afterwards. This is one D1 snapshot plus its immutable content-addressed referenced R2 objects; unreferenced R2 objects are omitted. Never enable public R2 access. Existing sessions are included; revoke them after recovery if appropriate.\n')
        # Media are immutable content-addressed keys. Missing any referenced object raises, never success.
        await self.cf_staff_commit(uid, 'SELECT 1', (), [self.cf_staff_audit(uid, 'backup', f'下载私密D1/R2备份（{len(media)}个媒体）')], ('admin', 'developer'))
        return Response(buffer.getvalue(), headers={'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="huali-d1-r2-backup.zip"', 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


STAFF_ROUTES = {
    '/api/tickets': (('GET','POST'), 'cf_staff_tickets'),
    '/api/ticket': (('GET',), 'cf_staff_ticket'),
    '/api/ticket/reply': (('POST',), 'cf_staff_reply'),
    '/api/ticket/resolve': (('POST',), 'cf_staff_resolve'),
    '/api/ticket/candidates': (('GET',), 'cf_staff_candidates'),
    '/api/ticket/link-order': (('POST',), 'cf_staff_link'),
    '/api/credit': (('POST',), 'cf_staff_credit'),
    '/api/credit/history': (('GET',), 'cf_staff_history'),
    '/api/review': (('POST',), 'cf_staff_review'),
    '/api/user/dossier': (('GET',), 'cf_staff_dossier'),
    '/api/admin/chats': (('GET',), 'cf_admin_chats'),
    '/api/admin/chat': (('GET',), 'cf_admin_chat'),
    '/api/admin/staff': (('GET','POST'), 'cf_staff_accounts'),
    '/api/admin/accounts': (('GET',), 'cf_staff_accounts'),
    '/api/admin/staff/status': (('POST',), 'cf_staff_account_action'),
    '/api/admin/staff/password': (('POST',), 'cf_staff_account_action'),
    '/api/admin/role': (('POST',), 'cf_staff_account_action'),
    '/api/admin/session/revoke': (('POST',), 'cf_staff_account_action'),
    '/api/admin/sellers': (('GET',), 'cf_staff_sellers'),
    '/api/admin/seller/delist': (('POST',), 'cf_staff_delist'),
    '/api/admin/sellers/moderate': (('POST',), 'cf_staff_delist'),
    '/api/admin/content/action': (('POST',), 'cf_staff_content'),
    '/api/moderation/words': (('GET','POST'), 'cf_staff_words'),
    '/api/admin/nominate': (('POST',), 'cf_staff_nominate'),
    '/api/admin/ban': (('POST',), 'cf_staff_ban'),
    '/api/admin/stars': (('POST',), 'cf_staff_stars'),
    '/api/admin/purge': (('POST',), 'cf_staff_purge'),
    '/api/audit/export': (('GET',), 'cf_staff_export'),
    '/api/backup': (('POST',), 'cf_staff_backup'),
}
