"""Operator workflows scoped to this domain."""
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

class CreditService:
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
