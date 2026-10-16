"""Account-owned transaction alerts written in the same transaction as the event."""
import time
from contextlib import closing


class Notifications:
    def notify(self, connection, recipients, event_key, title, entity_type, entity_id):
        for user_id in set(recipients) - {None}:
            connection.execute(
                'INSERT OR IGNORE INTO notifications(user_id,event_key,title,entity_type,entity_id,created_at) '
                'SELECT id,?,?,?,?,? FROM users WHERE id=? AND is_active=1',
                (event_key, title, entity_type, entity_id, time.time(), user_id),
            )

    def notifications(self, user_id, before=0):
        self.require(type(before) is int and before >= 0, '通知游标无效')
        with closing(self.connect()) as connection:
            connection.execute('BEGIN')
            rows = [dict(row) for row in connection.execute(
                'SELECT id,event_key,title,entity_type,entity_id,created_at,read_at FROM notifications '
                'WHERE user_id=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 51', (user_id, before, before),
            ).fetchall()]
            stats = dict(connection.execute('SELECT COALESCE(MAX(id),0) latest_id, '
                'COALESCE(SUM(read_at IS NULL),0) unread_count FROM notifications WHERE user_id=?', (user_id,)).fetchone())
        return {'items': rows[:50], 'has_more': len(rows) > 50, **stats}

    def read_notifications(self, user_id, payload):
        self.require(isinstance(payload, dict) and len(payload) == 1 and
                     set(payload) <= {'id', 'through_id'}, '请指定通知或本次已展示的通知范围')
        value = next(iter(payload.values()))
        self.require(type(value) is int and value > 0, '通知标识无效')
        with self.tx() as connection:
            if 'id' in payload:
                self.require(connection.execute('SELECT 1 FROM notifications WHERE id=? AND user_id=?',
                                                (value, user_id)).fetchone(), '通知不存在', 404)
                connection.execute('UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?',
                                   (time.time(), value, user_id))
            else:
                connection.execute('UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND id<=?',
                                   (time.time(), user_id, value))
        return {'ok': True}

    def notify_ticket(self, connection, ticket_id, event_key, title, actor=None, internal=False, queue=False):
        ticket = connection.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        participants = {ticket['user_id']}
        if ticket['order_id']:
            order = connection.execute('SELECT buyer_id,seller_id FROM orders WHERE id=?', (ticket['order_id'],)).fetchone()
            participants.update([order['buyer_id'], order['seller_id']])
        recipients = set() if internal else set(participants)
        # Queue events go to staff, while later activity goes to the assignee and administrators.
        staff = connection.execute("SELECT id,role FROM users WHERE is_active=1 AND role IN ('support','admin')").fetchall()
        for worker in staff:
            if worker['id'] not in participants and (queue or worker['role'] == 'admin' or worker['id'] == ticket['assignee']):
                recipients.add(worker['id'])
        self.notify(connection, recipients - {actor}, event_key, title, 'ticket', ticket_id)
