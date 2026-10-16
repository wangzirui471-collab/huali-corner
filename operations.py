"""Operator accounts, explicit physical returns and evidence-linked credit."""

import json
import time
import uuid
from decimal import Decimal


CREDIT_RULES = {
    'minor_issue': {'label': '首次轻微沟通失误', 'delta': 0},
    'no_show': {'label': '核实无故爽约（首次提醒，30天内重复扣5分）', 'delta': -5},
    'description_omission': {'label': '应说明的轻微描述遗漏', 'delta': -5},
    'hidden_defect': {'label': '隐瞒重要缺陷、缺页或功能问题', 'delta': -15},
    'outside_surcharge': {'label': '下单后强迫订单外加价', 'delta': -10},
    'forged_evidence': {'label': '核实故意伪造证据或恶意投诉', 'delta': -20},
    'fraud': {'label': '经核实的严重欺诈', 'delta': -50},
}


class Operations:
    def validate_evidence(self, user_id, upload_ids):
        self.require(isinstance(upload_ids, list) and len(upload_ids) <= 6, '每次最多提交6张证据图')
        self.require(all(isinstance(item, str) for item in upload_ids) and len(set(upload_ids)) == len(upload_ids), '证据标识无效')
        for upload_id in upload_ids:
            upload = self.row('SELECT user_id,private FROM uploads WHERE id=?', (upload_id,))
            self.require(upload and upload['user_id'] == user_id and upload['private'], '只能提交本人上传的私密证据图', 403)
        return upload_ids

    def save_evidence(self, connection, ticket_id, user_id, upload_ids, internal):
        count = connection.execute('SELECT COUNT(*) FROM ticket_evidence WHERE ticket_id=?', (ticket_id,)).fetchone()[0]
        self.require(count + len(upload_ids) <= 30, '单个工单证据图已达到上限')
        for upload_id in upload_ids:
            connection.execute('INSERT OR IGNORE INTO ticket_evidence VALUES(?,?,?,?,?)',
                               (ticket_id, upload_id, user_id, int(internal), time.time()))

    def can_view_evidence(self, user_id, upload_id):
        upload = self.row('SELECT user_id FROM uploads WHERE id=?', (upload_id,))
        if not upload:
            return False
        if upload['user_id'] == user_id:
            return True
        role = self.profile(user_id)['role']
        for row in self.rows('SELECT * FROM ticket_evidence WHERE upload_id=?', (upload_id,)):
            ticket = self.row('SELECT * FROM tickets WHERE id=?', (row['ticket_id'],))
            participants = {ticket['user_id']}
            if ticket['order_id']:
                order = self.row('SELECT buyer_id,seller_id FROM orders WHERE id=?', (ticket['order_id'],))
                participants.update([order['buyer_id'], order['seller_id']])
            if user_id in participants:
                if not row['internal']:
                    return True
            elif role == 'admin' or (role == 'support' and ticket['assignee'] == user_id):
                return True
        return False

    def assign_ticket(self, administrator_id, ticket_id, support_user_id, reason):
        self._administrator(administrator_id)
        ticket = self.ticket(administrator_id, ticket_id)
        self.check_conflict(administrator_id, ticket)
        worker = self.row('SELECT role,is_active FROM users WHERE id=?', (support_user_id,))
        self.require(worker and worker['role'] == 'support' and worker['is_active'], '请选择启用的专用客服账号')
        self.require(support_user_id != ticket['user_id'], '不能把工单指派给申请人')
        self.check_conflict(support_user_id, ticket)
        reason = self.text(reason, 1000, '指派依据')
        with self.tx() as connection:
            row = connection.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            self.require(row['status'] != 'resolved', '工单已结束')
            connection.execute("UPDATE tickets SET assignee=?,status='processing' WHERE id=?", (support_user_id, ticket_id))
            connection.execute('INSERT INTO audit(actor,target,type,reason,ticket_id,created) VALUES(?,?,?,?,?,?)',
                               (administrator_id, support_user_id, 'ticket_assignment', reason, ticket_id, time.time()))
            self.notify(connection,[support_user_id],f'ticket:{ticket_id}:assign:{connection.execute("SELECT MAX(id) FROM audit").fetchone()[0]}','有工单指派给你，请查看工作台','ticket',ticket_id)
        return self.ticket(administrator_id, ticket_id)

    def _administrator(self, user_id):
        self.require(self.profile(user_id)['role'] == 'admin', '仅平台管理员可操作', 403)

    def bootstrap_support(self, phone, password, nickname='转角客服'):
        self._trial_only()
        phone = self._phone(phone)
        self._password(password)
        nickname = self.text(nickname, 24, '客服昵称')
        salt, digest, rounds, recovery_digest, _ = self._new_credential(password)
        with self.tx() as connection:
            existing = connection.execute('SELECT id,role FROM users WHERE phone=?', (phone,)).fetchone()
            if existing:
                self.require(existing['role'] == 'support', '该号码已有账号，请使用独立客服号码', 409)
                user_id = existing['id']
            else:
                user_id = connection.execute("INSERT INTO users(phone,nickname,role) VALUES(?,?,'support')",
                                             (phone, nickname)).lastrowid
                connection.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',
                                   (user_id, salt, digest, rounds, recovery_digest))
        return self.profile(user_id)

    def create_support(self, administrator_id, payload):
        self._administrator(administrator_id)
        self.require(not (payload.keys() - {'phone', 'password', 'nickname'}), '客服资料含无效字段')
        result = self.bootstrap_support(payload.get('phone'), payload.get('password'), payload.get('nickname'))
        with self.tx() as connection:
            connection.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                               (administrator_id, result['id'], 'support_provision', '管理员配置独立客服账号', time.time()))
        return result

    def support_accounts(self, administrator_id):
        self._administrator(administrator_id)
        return self.rows("SELECT id,nickname,phone,is_active FROM users WHERE role='support' ORDER BY id")

    def set_support_active(self, administrator_id, user_id, is_active):
        self._administrator(administrator_id)
        self.require(type(is_active) is bool, '启用状态必须为布尔值')
        with self.tx() as connection:
            account = connection.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
            self.require(account and account['role'] == 'support', '仅可管理独立客服账号')
            connection.execute('UPDATE users SET is_active=? WHERE id=?', (int(is_active), user_id))
            if not is_active:
                connection.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            connection.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                               (administrator_id, user_id, 'support_active', '启用客服' if is_active else '停用客服并撤销会话', time.time()))
        return {'ok': True}

    def return_action(self, user_id, ticket_id, action):
        ticket = self.ticket(user_id, ticket_id)
        self.require(ticket['type'] == 'refund' and ticket['refund_mode'] == 'return_refund', '该工单不是退货退款')
        with self.tx() as connection:
            ticket = connection.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            self.require(ticket['status'] != 'resolved', '售后已结束')
            order = connection.execute('SELECT * FROM orders WHERE id=?', (ticket['order_id'],)).fetchone()
            self.require(order['delivered_at'], '尚未交付，无需退回实物')
            if action == 'return_sent':
                self.require(user_id == order['buyer_id'], '仅买家可标记已退回', 403)
                connection.execute('UPDATE tickets SET return_sent_at=COALESCE(return_sent_at,?) WHERE id=?',
                                   (time.time(), ticket_id))
            elif action == 'confirm_return':
                self.require(user_id == order['seller_id'], '仅卖家可确认收到实物', 403)
                self.require(ticket['return_sent_at'], '请先由买家记录已退回')
                connection.execute('UPDATE tickets SET return_received_at=COALESCE(return_received_at,?) WHERE id=?',
                                   (time.time(), ticket_id))
            else:
                self.require(False, '无效退货操作')
            connection.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',
                               (user_id, action, '交易当事人确认实物退回进度', ticket_id, time.time()))
            self.notify_ticket(connection,ticket_id,f'ticket:{ticket_id}:{action}','退货交接进度已更新',actor=user_id)
        return self.ticket(user_id, ticket_id)

    def _relist_source(self, connection, user_id, product_id):
        source = connection.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        self.require(source and source['seller_id'] == user_id, '商品不存在或不属于你', 403)
        self.require(source['status'] == 'removed', '该商品仍在售、交易中或已售出')
        eligible = False
        tickets = connection.execute(
            "SELECT o.items FROM tickets t JOIN orders o ON o.id=t.order_id WHERE o.seller_id=? "
            "AND o.status='refunded' AND t.status='resolved' AND t.outcome='refund' "
            "AND t.refund_mode='return_refund' AND t.return_received_at IS NOT NULL", (user_id,),
        ).fetchall()
        for row in tickets:
            if any(item['id'] == product_id for item in json.loads(row['items'])):
                eligible = True
                break
        self.require(eligible, '仅退款不恢复库存；须收到退货、退款完成且争议结束后重新上架')
        stock_key = source['stock_key'] or 'legacy:' + str(product_id)
        latest = connection.execute('SELECT MAX(id) AS id FROM products WHERE stock_key=?', (stock_key,)).fetchone()
        self.require(latest['id'] in (None, product_id), '该物品已有更新的出售记录，请查看最新商品的实物去向', 409)
        held = connection.execute("SELECT id FROM products WHERE stock_key=? AND status IN ('available','reserved','sold')",
                                  (stock_key,)).fetchone()
        self.require(not held, '这件实物已经重新上架、被预订或再次售出', 409)
        if not source['stock_key']:
            connection.execute('UPDATE products SET stock_key=? WHERE id=?', (stock_key, product_id))
            source = connection.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        return source

    def relist_draft(self, user_id, product_id):
        with self.tx() as connection:
            source = self._relist_source(connection, user_id, product_id)
            existing = connection.execute(
                "SELECT id FROM drafts WHERE user_id=? AND source_product_id=? AND status='active' AND updated_at>?",
                (user_id, product_id, time.time() - 30 * 86400),
            ).fetchone()
            if existing:
                draft_id = existing['id']
            else:
                data = json.loads(source['data'])
                fields = {name: str(data.get(name) or '') for name in [
                    'edition', 'publisher', 'notes', 'missing', 'accessories', 'bought', 'condition',
                    'author', 'isbn', 'course', 'major', 'college', 'description',
                ]}
                fields.update({name: source[name] for name in ['title', 'category', 'delivery', 'region']})
                fields['price'] = format(Decimal(source['price']) / 100, '.2f')
                fields['delivery_fee'] = format(Decimal(source['delivery_fee']) / 100, '.2f')
                fields['photos'] = [photo['id'] for photo in data.get('photos', [])]
                draft_id = uuid.uuid4().hex
                connection.execute('INSERT INTO drafts(id,user_id,fields,updated_at,source_product_id) VALUES(?,?,?,?,?)',
                                   (draft_id, user_id, json.dumps(fields, ensure_ascii=False), time.time(), product_id))
        return self.get_draft(user_id, draft_id)

    def seller_products(self, user_id):
        result = []
        for row in self.rows('SELECT id FROM products WHERE seller_id=? ORDER BY id DESC', (user_id,)):
            product = self.product(row['id'], user_id)
            product['can_relist'] = False
            if product['status'] == 'removed':
                with self.tx() as connection:
                    try:
                        self._relist_source(connection, user_id, product['id'])
                        product['can_relist'] = True
                    except Exception as error:
                        if not hasattr(error, 'status'):
                            raise
                        product['relist_reason'] = str(error)
            result.append(product)
        return result

    def _verified_credit_target(self, administrator_id, target_user_id, ticket_id, *, appeal=False):
        self._administrator(administrator_id)
        self.require(administrator_id != target_user_id, '不能处理自己的信誉', 403)
        ticket = self.ticket(administrator_id, ticket_id)
        self.check_conflict(administrator_id, ticket)
        self.require(ticket['status'] == 'resolved' and ticket['outcome'] in ['resolved', 'refund'], '请先核实工单并完成处理')
        related = set()
        if ticket['product_id']:
            related.add(self.product(ticket['product_id'])['seller_id'])
        if ticket['order_id']:
            order = self.order(administrator_id, ticket['order_id'])
            related.update([order['buyer_id'], order['seller_id']])
        if appeal:
            self.require(ticket['type'] == 'appeal', '必须关联已核实的申诉工单')
            related = {ticket['user_id']}
        else:
            self.require(ticket['type'] != 'appeal', '申诉不能直接作为扣分依据')
        self.require(target_user_id in related, '工单与该用户无处罚或复核关联')
        return ticket

    def apply_penalty(self, administrator_id, target_user_id, ticket_id, rule_key, reason):
        self._verified_credit_target(administrator_id, target_user_id, ticket_id)
        self.require(rule_key in CREDIT_RULES, '请选择明确的违规规则')
        reason = self.text(reason, 1000, '核实依据')
        with self.tx() as connection:
            duplicate = connection.execute(
                "SELECT 1 FROM audit WHERE target=? AND ticket_id=? AND type IN ('credit','credit_warning')",
                (target_user_id, ticket_id),
            ).fetchone()
            self.require(not duplicate, '该事件已处理，不能重复扣分或提醒', 409)
            delta = CREDIT_RULES[rule_key]['delta']
            if rule_key == 'no_show':
                previous = connection.execute(
                    "SELECT 1 FROM audit WHERE target=? AND rule_key='no_show' AND created>? "
                    "AND type IN ('credit','credit_warning') AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.reversal_of=audit.id)",
                    (target_user_id, time.time() - 30 * 86400),
                ).fetchone()
                if not previous:
                    delta = 0
            before = connection.execute('SELECT score FROM users WHERE id=?', (target_user_id,)).fetchone()['score']
            after = max(0, min(100, before + delta))
            connection.execute('UPDATE users SET score=? WHERE id=?', (after, target_user_id))
            if rule_key == 'fraud':
                connection.execute('UPDATE users SET trading_blocked=1 WHERE id=?', (target_user_id,))
                connection.execute("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (target_user_id,))
            audit_id = connection.execute(
                'INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created,rule_key,score_before,score_after) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (administrator_id, target_user_id, 'credit' if delta else 'credit_warning', after - before,
                 reason, ticket_id, time.time(), rule_key, before, after),
            ).lastrowid
        return {'audit_id': audit_id, 'credit_score': after, 'score_delta': after - before, 'is_warning': delta == 0}

    def reverse_penalty(self, administrator_id, audit_id, appeal_ticket_id, reason):
        self._administrator(administrator_id)
        original = self.row("SELECT * FROM audit WHERE id=? AND type IN ('credit','credit_warning')", (audit_id,))
        self.require(original and (original['delta'] or 0) <= 0, '原处罚不存在')
        target_user_id = original['target']
        self._verified_credit_target(administrator_id, target_user_id, appeal_ticket_id, appeal=True)
        reason = self.text(reason, 1000, '冲回依据')
        with self.tx() as connection:
            self.require(not connection.execute('SELECT 1 FROM audit WHERE reversal_of=?', (audit_id,)).fetchone(), '原处罚已经冲回', 409)
            before = connection.execute('SELECT score FROM users WHERE id=?', (target_user_id,)).fetchone()['score']
            after = min(100, before - (original['delta'] or 0))
            connection.execute('UPDATE users SET score=? WHERE id=?', (after, target_user_id))
            connection.execute(
                'INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created,rule_key,reversal_of,score_before,score_after) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (administrator_id, target_user_id, 'credit_reversal', after - before, reason, appeal_ticket_id,
                 time.time(), 'appeal_reversal', audit_id, before, after),
            )
            remaining = connection.execute(
                "SELECT 1 FROM audit WHERE target=? AND rule_key='fraud' AND type='credit' "
                "AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.reversal_of=audit.id)", (target_user_id,),
            ).fetchone()
            if original['rule_key'] == 'fraud' and not remaining:
                connection.execute('UPDATE users SET trading_blocked=0 WHERE id=?', (target_user_id,))
        return {'credit_score': after, 'score_delta': after - before}

    def recover_credit(self, administrator_id, target_user_id, ticket_id, reason):
        self._verified_credit_target(administrator_id, target_user_id, ticket_id, appeal=True)
        reason = self.text(reason, 1000, '整改复核依据')
        with self.tx() as connection:
            recent = connection.execute(
                "SELECT 1 FROM audit WHERE target=? AND created>? AND ((type='credit' AND delta<0) OR type='credit_recovery') "
                "AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.reversal_of=audit.id)",
                (target_user_id, time.time() - 30 * 86400),
            ).fetchone()
            self.require(not recent, '需整改后连续30天无新增核实违规，且每30天最多恢复一次')
            blocked = connection.execute('SELECT trading_blocked,score FROM users WHERE id=?', (target_user_id,)).fetchone()
            self.require(not blocked['trading_blocked'], '严重欺诈限制需先单独申诉复核')
            before = blocked['score']
            self.require(before < 100, '信誉已达100分')
            after = min(100, before + 5)
            connection.execute('UPDATE users SET score=? WHERE id=?', (after, target_user_id))
            connection.execute(
                'INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created,rule_key,score_before,score_after) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (administrator_id, target_user_id, 'credit_recovery', after - before, reason, ticket_id,
                 time.time(), 'manual_recovery', before, after),
            )
        return {'credit_score': after, 'score_delta': after - before}
