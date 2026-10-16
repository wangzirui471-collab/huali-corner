"""Viewer-specific chat names and durable, bounded read acknowledgements."""
import time


class ChatInbox:
    def room_view(self, user_id, room):
        view = dict(room)
        if view['kind'] == 'private':
            peer = self.row('SELECT u.id,u.nickname FROM members m JOIN users u ON u.id=m.user_id '
                            'WHERE m.room_id=? AND m.user_id<>?', (view['id'], user_id))
            view['name'] = peer['nickname']
            view['peer_id'] = peer['id']
        member = self.member(user_id, view['id'])
        view['unread_count'] = self.row('SELECT COUNT(*) n FROM messages WHERE room_id=? AND id>? '
            'AND user_id<>? AND removed=0', (view['id'], member['last_read_message_id'], user_id))['n']
        view['last_message'] = self.row("SELECT id,CASE WHEN removed=1 THEN '消息已被移除' ELSE body END body,created "
                                        'FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 1', (view['id'],))
        return view

    def read_messages(self, user_id, room_id, through_id):
        self.require(type(through_id) is int and through_id > 0, '消息已读游标无效')
        with self.tx() as connection:
            member = connection.execute('SELECT * FROM members WHERE room_id=? AND user_id=?', (room_id, user_id)).fetchone()
            self.require(member, '请先加入该会话', 403)
            self.require(connection.execute('SELECT 1 FROM messages WHERE room_id=? AND id=?', (room_id, through_id)).fetchone(),
                         '只能标记本会话已展示的消息')
            connection.execute('UPDATE members SET last_read_message_id=MAX(last_read_message_id,?) WHERE room_id=? AND user_id=?',
                               (through_id, room_id, user_id))
            connection.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND entity_type='chat' "
                "AND entity_id=? AND event_key IN (SELECT 'chat:'||room_id||':message:'||id FROM messages WHERE room_id=? AND id<=?)",
                (time.time(), user_id, room_id, room_id, through_id))
        return {'ok': True}
