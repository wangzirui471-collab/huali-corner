"""人员与权限：平台侧账号（客服 / 管理员）的创建、停用、重置与下线。

与 support/service.py 的分工：
    support  —— 面向**普通用户**的处置（封禁、信誉、工单）；
    staff    —— 面向**平台自己人**的授权（建号、停用、重置、踢会话）。

这个区分是必要的：封禁（ban）是「这个人违规了」，停用（disabled）是
「这个客服不在岗了 / 离职了」。用封禁去处理离职是一种语义污染——
它会触发下架全部商品、关闭在途订单那一整套买家保护流程，
而离职客服的账号里根本没有商品和订单。
"""
import secrets
import time

from ..core.errors import ValidationMixin

ROLE_NAMES = {'support': '客服', 'admin': '平台管理员'}
STAFF_ROLES = ('support', 'admin')


class StaffService(ValidationMixin):

    def staff_accounts(self, u):
        """运营账号清单。只有管理员能看——客服不需要知道还有谁在后台。"""
        self.admin(u)
        now = time.time()
        rows = self.rows(
            """SELECT u.id,u.phone,u.nickname,u.role,u.status,u.last_login,
                      (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id AND s.expires>?) sessions
               FROM users u WHERE u.role IN ('support','admin') ORDER BY u.role DESC, u.id""",
            (now,))
        for r in rows:
            r['role_name'] = ROLE_NAMES.get(r['role'], r['role'])
            r['online'] = bool(r['sessions'])
        return rows

    def create_staff(self, u, d):
        """新建客服或管理员账号。

        口令由管理员当场设定（不用随机生成再想办法传出去——那样只能贴在聊天里）。
        恢复码仍然返回一次，让当事人自己保存：否则忘了密码又得找管理员重置。
        """
        self.admin(u)
        role = d.get('role') or 'support'
        self.require(role in STAFF_ROLES, '角色只能是客服（support）或管理员（admin）')
        phone = self._phone(d.get('phone'))
        password = self._password(d.get('password'))
        nickname = self.text(d.get('nickname'), 24, '昵称')
        salt, digest, rounds, recovery_digest, recovery = self._new_credential(password)
        with self.tx() as c:
            self.require(not c.execute('SELECT 1 FROM users WHERE phone=?', (phone,)).fetchone(),
                         '此账号已注册，请直接调整其角色', 409)
            uid = c.execute(
                "INSERT INTO users(phone,nickname,role,college,status) VALUES(?,?,?,'计算机工程学院','active')",
                (phone, nickname, role)).lastrowid
            c.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',
                      (uid, salt, digest, rounds, recovery_digest))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, uid, 'staff_create', f'创建{ROLE_NAMES[role]}账号「{nickname}」', time.time()))
        return {'id': uid, 'phone': phone, 'role': role, 'recovery_code': recovery}

    def set_staff_status(self, u, target, status):
        """停用 / 启用运营账号。

        停用而不是封禁：账号不再能登录，但不动它在其他表里的痕迹（审计、工单记录）。
        停用会立刻删除它的全部会话——「你被停用了」这句话必须当场生效，
        否则对方还能拿着现有令牌继续操作到令牌过期（最长 7 天）。
        """
        self.admin(u)
        target = int(target)
        self.require(status in ('active', 'disabled'), '状态只能是 active（启用）或 disabled（停用）')
        self.require(target != u, '不能停用自己的账号；需要交出权限请让另一位管理员操作')
        with self.tx() as c:
            user = c.execute('SELECT id,role,nickname,status FROM users WHERE id=?', (target,)).fetchone()
            self.require(user, '账号不存在', 404)
            self.require(user['role'] in STAFF_ROLES, '这里只管理客服与管理员账号；普通用户请到用户分区处理', 400)
            # 不需要额外的「最后一个管理员」保护：操作者自己必须是在岗管理员，
            # 且不能停用自己，所以「停用之后一个管理员都不剩」只可能发生在
            # 停用自己时——那条上面已经拦掉了。写一个永远为真的检查只会误导后人。
            now = time.time()
            c.execute('UPDATE users SET status=? WHERE id=?', (status, target))
            if status == 'disabled':
                c.execute('DELETE FROM sessions WHERE user_id=?', (target,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, target, 'staff_disable' if status == 'disabled' else 'staff_enable',
                       f'{"停用" if status == "disabled" else "启用"}{ROLE_NAMES[user["role"]]}账号「{user["nickname"]}」', now))
        return self.profile(target)

    def reset_staff_password(self, u, target):
        """重置运营账号口令，并踢掉它的全部会话。

        返回的临时口令只在这里出现一次，服务端不存明文——存了就等于
        「管理员随时能看到别人的密码」，那是比忘记密码更严重的问题。
        """
        self.admin(u)
        target = int(target)
        self.require(target != u, '重置自己的密码请走「我的 → 修改密码」，那里需要验证原密码')
        user = self.profile(target)
        self.require(user['role'] in STAFF_ROLES, '这里只重置客服与管理员账号；普通用户请用恢复码自助找回', 400)
        account = self.row('SELECT phone FROM users WHERE id=?', (target,))
        temp = secrets.token_urlsafe(9)          # 12 个字符，满足 6 位下限
        self._password(temp)
        salt, digest, rounds, recovery_digest, recovery = self._new_credential(temp)
        with self.tx() as c:
            c.execute('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',
                      (salt, digest, rounds, recovery_digest, target))
            c.execute('DELETE FROM sessions WHERE user_id=?', (target,))
            c.execute('DELETE FROM auth_attempts WHERE phone=?', (account['phone'],))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, target, 'staff_password_reset',
                       f'重置{ROLE_NAMES[user["role"]]}账号「{user["nickname"]}」的密码', time.time()))
        return {'password': temp, 'recovery_code': recovery}

    def revoke_sessions(self, u, target):
        """强制下线：删掉该账号的全部会话，它在任何设备上都需要重新登录。

        这是「封禁」之外缺的那一档：盗号、手机丢在教室、正在群里刷广告——
        封号会下架他全部商品、关掉在途订单，太重；踢下线刚好。
        """
        self.staff(u)
        target = int(target)
        self.require(target != u, '要退出自己的登录请使用「退出」按钮')
        user = self.profile(target)
        if user['role'] in STAFF_ROLES:
            # 踢同事下线等于中断他正在做的处置，必须管理员决定。
            self.require(self.profile(u)['role'] == 'admin', '只有平台管理员可以强制下线客服或管理员账号', 403)
        with self.tx() as c:
            count = c.execute('SELECT COUNT(*) n FROM sessions WHERE user_id=?', (target,)).fetchone()['n']
            c.execute('DELETE FROM sessions WHERE user_id=?', (target,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, target, 'session_revoke', f'强制下线「{user["nickname"]}」，注销 {count} 个会话', time.time()))
        return {'revoked': count}
