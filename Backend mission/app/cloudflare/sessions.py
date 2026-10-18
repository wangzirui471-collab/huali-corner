"""会话解析：把 Authorization: Bearer <token> 还原成用户。

sessions 表只存 sha256(token)，明文 token 只在客户端。所以这里必须先摘要再查。
过期的会话视为未登录，并顺手删掉，避免表无限增长。
"""
import time

from .crypto import session_digest

__all__ = ['current_user_id', 'require_user_id', 'issue_session', 'revoke_session']

ACTIVE_STATUSES = ('active',)


def _bearer(request):
    header = request.headers.get('Authorization') or ''
    if not header.startswith('Bearer '):
        return None
    token = header[7:].strip()
    return token or None


async def current_user_id(db, request):
    """返回 (user_id, status)；未登录返回 (None, None)。"""
    token = _bearer(request)
    if not token:
        return None, None
    digest = session_digest(token)
    row = await db.first('SELECT user_id, expires FROM sessions WHERE token=?', (digest,))
    if not row:
        return None, None
    if float(row['expires'] or 0) <= time.time():
        await db.run('DELETE FROM sessions WHERE token=?', (digest,))
        return None, None
    status_row = await db.first('SELECT status FROM users WHERE id=?', (row['user_id'],))
    if not status_row:
        return None, None
    return row['user_id'], status_row['status']


async def require_user_id(db, request):
    uid, status = await current_user_id(db, request)
    if uid is None:
        from .http import ApiError
        raise ApiError('请先登录', 401)
    if status != 'active':
        from .http import ApiError
        raise ApiError('账号状态异常，请联系管理员', 403)
    return uid


async def issue_session(db, user_id, token, ttl):
    await db.run(
        'INSERT OR REPLACE INTO sessions(token,user_id,expires) VALUES(?,?,?)',
        (session_digest(token), int(user_id), time.time() + ttl),
    )
    return token


async def revoke_session(db, request):
    token = _bearer(request)
    if token:
        await db.run('DELETE FROM sessions WHERE token=?', (session_digest(token),))
