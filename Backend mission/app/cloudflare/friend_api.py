"""好友系统（2026-10 新增）：申请、同意/拒绝、好友门禁。

与论坛「求购 · 我能卖」联动：卖方回应求购时，附上 want_id 发起好友申请，
对方同意后才能私聊协商。这是原需求里「同意前只能带 ≤15 字附言、不能发图、
同意后才能私聊」的落地点。
"""
import time

from ..core.errors import DomainError
from ..moderation import scan_private
from .http import json_response, json_body, query_of, int_param, require

FRIEND_MESSAGE_LIMIT = 15


class FriendApi:
    async def _friend_row(self, uid, target):
        return await self.db.first(
            "SELECT * FROM friendships WHERE (requester=? AND target=?) OR (requester=? AND target=?) "
            "ORDER BY id DESC LIMIT 1", (uid, target, target, uid))

    async def cf_is_friend(self, uid, peer):
        return bool(await self.db.first(
            "SELECT 1 FROM friendships WHERE status='accepted' AND ((requester=? AND target=?) OR (requester=? AND target=?))",
            (uid, peer, peer, uid)))

    async def cf_friends(self, r):
        """好友列表 + 收到/发出的申请。只给公开资料字段。"""
        uid = await self.page_user(r)
        rows = await self.db.all(
            """SELECT f.*,u.nickname,u.college,u.major,u.grade,u.score
               FROM friendships f JOIN users u ON u.id=CASE WHEN f.requester=? THEN f.target ELSE f.requester END
               WHERE f.requester=? OR f.target=? ORDER BY COALESCE(f.decided,f.created) DESC""", (uid, uid, uid))
        out = {'friends': [], 'incoming': [], 'outgoing': []}
        for row in rows:
            peer = row['target'] if row['requester'] == uid else row['requester']
            item = {'id': row['id'], 'user_id': peer, 'nickname': row['nickname'], 'college': row['college'],
                    'major': row['major'], 'grade': row['grade'], 'score': row['score'], 'message': row['message'],
                    'want_id': row['want_id'], 'status': row['status'], 'created': row['created'],
                    'decided': row['decided']}
            if row['status'] == 'accepted':
                out['friends'].append(item)
            elif row['status'] == 'pending':
                (out['incoming'] if row['target'] == uid else out['outgoing']).append(item)
        return json_response(out)

    async def cf_friend_state(self, r):
        """给前端决定按钮文案：self/accepted/pending_out/pending_in/none。"""
        uid = await self.page_user(r)
        q = query_of(r)
        target = int_param(q, 'id')
        if target == uid:
            return json_response({'state': 'self'})
        row = await self._friend_row(uid, target)
        if not row or row['status'] == 'rejected':
            return json_response({'state': 'none'})
        if row['status'] == 'accepted':
            return json_response({'state': 'accepted'})
        return json_response({'state': 'pending_out' if row['requester'] == uid else 'pending_in'})

    async def cf_friend_request(self, r):
        uid = await self.page_user(r)
        d = await json_body(r)
        target = int(d.get('target') or 0)
        require(target and target != uid, '不能加自己为好友')
        require(await self.db.first("SELECT 1 FROM users WHERE id=? AND status='active'", (target,)), '用户不存在', 404)
        message = str(d.get('message') or '').strip()
        require(len(message) <= FRIEND_MESSAGE_LIMIT, f'申请附言最多 {FRIEND_MESSAGE_LIMIT} 个字')
        if message:
            require(not scan_private(message)['blocked'], '申请附言包含不能发送的内容', 422)
        want_id = int(d.get('want_id') or 0)
        if want_id:
            require(await self.db.first('SELECT 1 FROM wants WHERE id=?', (want_id,)), '求购不存在', 404)

        now = time.time()
        row = await self._friend_row(uid, target)
        if row and row['status'] == 'accepted':
            return json_response({'ok': True, 'state': 'accepted', 'message': '你们已经是好友'})
        if row and row['status'] == 'pending':
            if row['requester'] == uid:
                return json_response({'ok': True, 'state': 'pending_out', 'message': '申请已发送，等对方处理'})
            return json_response({'ok': True, 'state': 'pending_in', 'message': '对方已向你发出申请，去「好友」处理'})

        nick = (await self.db.first('SELECT nickname FROM users WHERE id=?', (uid,)))['nickname']
        body = nick + ' 想加你为好友' + (f'：{message}' if message else '')
        # 同时写申请与通知，失败（并发重复）则整体回滚。
        if row:
            stmts = [
                ("UPDATE friendships SET requester=?,target=?,message=?,want_id=?,status='pending',created=?,decided=NULL WHERE id=?",
                 (uid, target, message, want_id, now, row['id'])),
                ('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)', (target, 'friend_request', body, now)),
            ]
        else:
            stmts = [
                ("INSERT INTO friendships(requester,target,message,want_id,status,created) VALUES(?,?,?,?,?,?)",
                 (uid, target, message, want_id, 'pending', now)),
                ('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)', (target, 'friend_request', body, now)),
            ]
        guard = "SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM friendships WHERE status='pending' AND ((requester=? AND target=?) OR (requester=? AND target=?)))"
        await self.db.guarded_batch(guard, (uid, target, target, uid), stmts)
        return json_response({'ok': True, 'state': 'pending_out', 'message': '申请已发送'})

    async def cf_friend_decide(self, r):
        uid = await self.page_user(r)
        d = await json_body(r)
        fid = int(d.get('id') or 0)
        accept = bool(d.get('accept', True))
        row = await self.db.first('SELECT * FROM friendships WHERE id=?', (fid,))
        require(row, '申请不存在', 404)
        require(row['target'] == uid, '只能处理发给你的申请', 403)
        require(row['status'] == 'pending', '该申请已处理')
        now = time.time()
        nick = (await self.db.first('SELECT nickname FROM users WHERE id=?', (uid,)))['nickname']
        notice = (nick + ' 同意了你的好友申请，现在可以聊天了') if accept else '对方拒绝了你的好友申请'
        await self.db.guarded_batch(
            "SELECT 1 FROM friendships WHERE id=? AND status='pending'", (fid,),
            [('UPDATE friendships SET status=?,decided=? WHERE id=?', ('accepted' if accept else 'rejected', now, fid)),
             ('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)', (row['requester'], 'friend_accepted' if accept else 'friend_rejected', notice, now))])
        return json_response({'ok': True, 'status': 'accepted' if accept else 'rejected'})


FRIEND_ROUTES = {
    '/api/friends': (('GET',), 'cf_friends'),
    '/api/friend/state': (('GET',), 'cf_friend_state'),
    '/api/friend/request': (('POST',), 'cf_friend_request'),
    '/api/friend/decide': (('POST',), 'cf_friend_decide'),
}
