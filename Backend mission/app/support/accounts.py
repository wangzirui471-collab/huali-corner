"""Operator workflows scoped to this domain."""
import json
import time
import uuid
from decimal import Decimal


class SupportAccounts:
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
