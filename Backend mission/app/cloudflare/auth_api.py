"""Credential rotation and retained-data account deactivation for D1."""
import hashlib
import secrets
import time
from . import crypto, sessions
from .http import json_body, json_response, query_of, require


class AuthApi:
    async def cf_auth_salt(self, request):
        query = query_of(request)
        if 'phone' in query:
            account = self.normalize_account(query['phone'])
            row = await self.db.first(
                'SELECT p.salt,p.rounds FROM password_credentials p '
                'JOIN users u ON u.id=p.user_id WHERE u.phone=?', (account,))
        else:
            uid = await self.page_user(request)
            row = await self.db.first(
                'SELECT salt,rounds FROM password_credentials WHERE user_id=?', (uid,))
            require(row, '账号没有密码凭据，请联系管理员', 404)
        return json_response({'salt': row['salt'] if row else '00' * 16,
                              'rounds': int(row['rounds']) if row else crypto.ROUNDS})

    def cf_auth_new_credential(self, data):
        salt = self.check_salt(data.get('salt'))
        digest = self.check_digest(data.get('digest'))
        require(type(data.get('rounds')) is int and data['rounds'] == crypto.ROUNDS,
                '新密码必须使用600000轮PBKDF2派生')
        recovery = secrets.token_urlsafe(32)
        recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()
        return salt, digest, crypto.ROUNDS, recovery_digest, recovery

    async def cf_auth_password(self, request):
        uid = await self.page_user(request)
        data = await json_body(request)
        old_digest = self.check_digest(data.get('old_digest'))
        salt, digest, rounds, recovery_digest, recovery = self.cf_auth_new_credential(data)
        row = await self.db.first('SELECT digest,recovery_digest FROM password_credentials WHERE user_id=?', (uid,))
        require(row and crypto.constant_time_equals(old_digest, row['digest']), '原密码不正确', 401)
        # The original credential and active session are checked in the same D1
        # transaction as rotation and revocation. Two resets cannot both succeed.
        token_digest = crypto.session_digest(sessions._bearer(request))
        await self.db.guarded_batch(
            "SELECT 1 FROM password_credentials p JOIN users u ON u.id=p.user_id "
            "WHERE p.user_id=? AND p.digest=? AND p.recovery_digest=? AND u.status='active' "
            'AND EXISTS(SELECT 1 FROM sessions WHERE token=? AND user_id=u.id AND expires>?)',
            (uid, old_digest, row['recovery_digest'], token_digest, time.time()), [
                ('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',
                 (salt, digest, rounds, recovery_digest, uid)),
                ('DELETE FROM sessions WHERE user_id=?', (uid,)),
                ('DELETE FROM auth_attempts WHERE phone=(SELECT phone FROM users WHERE id=?)', (uid,)),
            ], message='密码或登录状态已变化，请重新登录后重试')
        return json_response({'ok': True, 'recovery_code': recovery})

    async def cf_auth_recover(self, request):
        data = await json_body(request)
        account = self.normalize_account(data.get('phone'))
        code = data.get('recovery_code')
        require(isinstance(code, str) and 0 < len(code) <= 128, '账号、密码或恢复码不正确', 401)
        salt, digest, rounds, recovery_digest, recovery = self.cf_auth_new_credential(data)
        candidate = hashlib.sha256(code.encode('utf-8')).hexdigest()
        row = await self.db.first(
            'SELECT p.user_id,p.recovery_digest,u.status FROM password_credentials p '
            'JOIN users u ON u.id=p.user_id WHERE u.phone=?', (account,))
        require(row and crypto.constant_time_equals(candidate, row['recovery_digest']),
                '账号、密码或恢复码不正确', 401)
        require(row['status'] == 'active', '账号状态异常，请联系管理员', 403)
        uid = row['user_id']
        await self.db.guarded_batch(
            "SELECT 1 FROM password_credentials p JOIN users u ON u.id=p.user_id "
            "WHERE p.user_id=? AND p.recovery_digest=? AND u.status='active' AND u.phone=?",
            (uid, candidate, account), [
                ('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',
                 (salt, digest, rounds, recovery_digest, uid)),
                ('DELETE FROM sessions WHERE user_id=?', (uid,)),
                ('DELETE FROM auth_attempts WHERE phone=?', (account,)),
            ], message='恢复码或账号状态已变化，请使用最新恢复码重试')
        return json_response({'ok': True, 'recovery_code': recovery})

    async def cf_auth_deactivate(self, request):
        uid = await self.page_user(request)
        order_check = """NOT EXISTS(SELECT 1 FROM orders WHERE (buyer_id=? OR seller_id=?)
            AND status NOT IN ('completed','cancelled','refunded','partial_refunded'))"""
        ticket_check = """NOT EXISTS(SELECT 1 FROM tickets t LEFT JOIN orders o ON o.id=t.order_id
            WHERE t.status NOT IN ('resolved','rejected')
            AND (t.user_id=? OR o.buyer_id=? OR o.seller_id=?))"""
        admin_check = """(u.role<>'admin' OR EXISTS(
            SELECT 1 FROM users other WHERE other.id<>u.id AND other.role='admin' AND other.status='active'))"""
        require(await self.db.scalar('SELECT ' + order_check, (uid, uid)),
                '还有未完成的订单，请先处理或申请售后后再注销')
        require(await self.db.scalar('SELECT ' + ticket_check, (uid, uid, uid)),
                '还有未结案的工单，请等待处理完成后再注销')
        require(await self.db.first('SELECT 1 FROM users u WHERE id=? AND '+admin_check, (uid,)),
                '最后一名在岗管理员不能注销，请先安排其他管理员')
        token_digest = crypto.session_digest(sessions._bearer(request))
        await self.db.guarded_batch(
            "SELECT 1 FROM users u WHERE u.id=? AND u.status='active' AND " + order_check +
            ' AND ' + ticket_check + ' AND ' + admin_check +
            ' AND EXISTS(SELECT 1 FROM sessions WHERE token=? AND user_id=u.id AND expires>?)',
            (uid, uid, uid, uid, uid, uid, token_digest, time.time()), [
                ("UPDATE users SET status='deactivated' WHERE id=?", (uid,)),
                ('DELETE FROM sessions WHERE user_id=?', (uid,)),
                ("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'", (uid,)),
            ], message='订单、工单或账号状态已变化，请处理完成后再注销')
        return json_response({'ok': True})


AUTH_ROUTES = {
    '/api/auth/salt': (('GET',), 'cf_auth_salt'),
    '/api/auth/password': (('POST',), 'cf_auth_password'),
    '/api/auth/recover': (('POST',), 'cf_auth_recover'),
    '/api/auth/deactivate': (('POST',), 'cf_auth_deactivate'),
}
