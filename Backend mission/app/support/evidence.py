"""Operator workflows scoped to this domain."""
import json
import time
import uuid
from decimal import Decimal


class TicketEvidence:
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
