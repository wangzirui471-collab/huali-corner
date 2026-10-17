"""账号模块：注册、登录、改密、恢复码、个人资料与角色权限。

密码认证来自原 auth.py 的 PasswordAuth，账号接口来自原 market.py。
"""
import hashlib
import re
import secrets
import time

ROUNDS=600000
import hashlib, re, secrets, time
from ..core.errors import ValidationMixin, DomainError
from .credit import is_trusted, star_badge


class AccountService(ValidationMixin):

    def trusted_map(self, seller_ids):
        """批量判定「诚信客户」，返回 {seller_id: bool}。

        商品流一页几十件，逐个卖家查「发布数 + 交付表现」会变成 N+1；
        这里按卖家集合一次查完。规则见 account/credit.py：
        发布 ≥ 10 件、至少 1 笔交付、全部按时、无退款。
        封禁/注销账号直接排除——标签是给正常经营的账号看的。
        """
        ids=[int(x) for x in set(seller_ids or []) if x]
        if not ids:return {}
        marks=','.join('?'*len(ids));args=tuple(ids)
        stats={i:{'listings':0,'delivered':0,'late':0,'refunded':0} for i in ids}
        for r in self.rows('SELECT seller_id,COUNT(*) n FROM products WHERE seller_id IN (%s) GROUP BY seller_id'%marks,args):
            stats[r['seller_id']]['listings']=r['n']
        # delivered：真正发生过交付的订单。老数据可能没有 delivered_at，
        # 但状态已进入「待收货/已完成/退款」也说明交付过，一并计入。
        # late：卖家标记交付的时间晚于约定时间。
        # refunded：退款订单单独计数，出现即失去标签。
        for r in self.rows(
            'SELECT seller_id,'
            " SUM(CASE WHEN delivered_at IS NOT NULL OR handover_at IS NOT NULL"
            " OR status IN ('awaiting_receipt','completed','refunded','partial_refunded') THEN 1 ELSE 0 END) delivered,"
            " SUM(CASE WHEN delivered_at IS NOT NULL AND appointment>0 AND delivered_at>appointment THEN 1 ELSE 0 END) late,"
            " SUM(CASE WHEN status IN ('refunded','partial_refunded') THEN 1 ELSE 0 END) refunded"
            ' FROM orders WHERE seller_id IN (%s) GROUP BY seller_id'%marks,args):
            stats[r['seller_id']].update(delivered=r['delivered'] or 0,late=r['late'] or 0,refunded=r['refunded'] or 0)
        inactive={r['id'] for r in self.rows("SELECT id FROM users WHERE id IN (%s) AND status<>'active'"%marks,args)}
        return {i:(i not in inactive) and is_trusted(**v) for i,v in stats.items()}

    # 账号不可用时的提示。三种状态的含义完全不同，混成一句「已注销或已被封禁」
    # 会让被停用的客服以为自己被封号了，直接去找人吵架。
    STATUS_MESSAGES = {
        'banned': '该账号已被封禁，如有异议可在客服中心申诉',
        'deactivated': '该账号已注销',
        'disabled': '该账号已被平台停用，请联系管理员',
    }

    @classmethod
    def status_message(cls, status):
        return cls.STATUS_MESSAGES.get(status, '账号状态异常，请联系管理员')

    def _trial_only(self):self.require(self.trial,'此接口仅供学院试用版使用',403)
    # 账号标识：11 位手机号，或邮箱地址。
    # 校园里不少同学习惯用邮箱记账号，运营者的调试账号也用邮箱更好记；
    # 邮箱统一转小写，避免同一个邮箱因大小写差异被当成两个账号。
    # 注意：request_code（短信验证码）仍只认手机号，邮箱收不到短信。
    _PHONE_RE=re.compile(r'1[3-9][0-9]{9}')
    _EMAIL_RE=re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')
    def _phone(self,phone):
        if isinstance(phone,str):phone=phone.strip()
        if isinstance(phone,str) and self._EMAIL_RE.fullmatch(phone):
            self.require(len(phone)<=120,'邮箱地址过长')
            return phone.lower()
        self.require(isinstance(phone,str) and self._PHONE_RE.fullmatch(phone),'请输入11位手机号或邮箱')
        return phone
    def _password(self,password):
        # 下限取 6：原先是 12，对校园试用来讲太苛刻（用户反馈记不住）。
        # 6 是常见的最低门槛，再往下就没有意义了——上限 128 保持不变。
        self.require(isinstance(password,str) and 6<=len(password)<=128,'密码需为6至128个字符，不要使用其他网站的密码')
        return password
    @staticmethod
    def _derive(password,salt,rounds=ROUNDS):
        return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),rounds).hex()
    def _new_credential(self,password):
        salt=secrets.token_hex(16);recovery=secrets.token_urlsafe(32)
        return salt,self._derive(password,salt),ROUNDS,hashlib.sha256(recovery.encode()).hexdigest(),recovery
    def _session(self,c,uid):
        token=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400*7))
        return token
    def _trial_result(self,uid,token,recovery=None):
        result={'token':token,'user':self.profile(uid),'simulation':True,'phone_verified':False}
        if recovery:result['recovery_code']=recovery
        return result
    def _lock_check(self,c,phone):
        row=c.execute('SELECT * FROM auth_attempts WHERE phone=?',(phone,)).fetchone()
        self.require(not row or row['reset_at']<=time.time() or row['attempts']<5,'尝试次数过多，请15分钟后重试或使用恢复码',429)
    def _failed_auth(self,c,phone):
        now=time.time();row=c.execute('SELECT * FROM auth_attempts WHERE phone=?',(phone,)).fetchone()
        attempts=row['attempts']+1 if row and row['reset_at']>now else 1
        reset_at=row['reset_at'] if row and row['reset_at']>now else now+900
        c.execute('INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?)',(phone,attempts,reset_at))
        # Failed-attempt accounting must survive the domain error/transaction rollback.
        c.commit()
        self.require(False,'账号、密码或恢复码不正确',401)
    def register_password(self,phone,password,nickname):
        self._trial_only();phone=self._phone(phone);self._password(password)
        nickname=self.text(nickname,24,'昵称');salt,digest,rounds,recovery_digest,recovery=self._new_credential(password)
        with self.tx() as c:
            self.require(not c.execute('SELECT 1 FROM users WHERE phone=?',(phone,)).fetchone(),'此账号已注册，请登录或使用恢复码',409)
            uid=c.execute("INSERT INTO users(phone,nickname,college,role) VALUES(?,?,'计算机工程学院','user')",(phone,nickname)).lastrowid
            c.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',(uid,salt,digest,rounds,recovery_digest))
            token=self._session(c,uid)
        return self._trial_result(uid,token,recovery)
    def login_password(self,phone,password):
        self._trial_only();phone=self._phone(phone)
        self.require(isinstance(password,str) and len(password)<=128,'账号、密码或恢复码不正确',401)
        with self.connect() as c:self._lock_check(c,phone)
        credential=self.row('SELECT p.*,u.status FROM password_credentials p JOIN users u ON u.id=p.user_id WHERE u.phone=?',(phone,))
        # Perform the KDF even for an unknown phone; do not disclose account existence.
        digest=self._derive(password,credential['salt'] if credential else '00'*16,credential['rounds'] if credential else ROUNDS)
        with self.tx() as c:
            self._lock_check(c,phone)
            current=c.execute('SELECT p.*,u.status FROM password_credentials p JOIN users u ON u.id=p.user_id WHERE u.phone=?',(phone,)).fetchone()
            if not current or not secrets.compare_digest(current['digest'],digest):self._failed_auth(c,phone)
            self.require(current['status']=='active',self.status_message(current['status']),403)
            now=time.time()
            c.execute('DELETE FROM auth_attempts WHERE phone=?',(phone,));uid=current['user_id'];token=self._session(c,uid)
            c.execute('UPDATE users SET last_login=? WHERE id=?',(now,uid))
        return self._trial_result(uid,token)
    def change_password(self,uid,old_password,new_password):
        self._trial_only();self._password(new_password)
        self.require(isinstance(old_password,str) and len(old_password)<=128,'原密码不正确',401)
        credential=self.row('SELECT * FROM password_credentials WHERE user_id=?',(uid,))
        self.require(credential,'账号不存在',401)
        digest=self._derive(old_password,credential['salt'],credential['rounds'])
        salt,new_digest,rounds,recovery_digest,recovery=self._new_credential(new_password)
        with self.tx() as c:
            current=c.execute('SELECT digest FROM password_credentials WHERE user_id=?',(uid,)).fetchone()
            self.require(current and secrets.compare_digest(current['digest'],digest),'原密码不正确',401)
            c.execute('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',(salt,new_digest,rounds,recovery_digest,uid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            c.execute('DELETE FROM auth_attempts WHERE phone=(SELECT phone FROM users WHERE id=?)',(uid,))
        return {'ok':True,'recovery_code':recovery}
    def recover_password(self,phone,recovery_code,new_password):
        self._trial_only();phone=self._phone(phone);self._password(new_password)
        self.require(isinstance(recovery_code,str) and len(recovery_code)<=128,'账号、密码或恢复码不正确',401)
        candidate=hashlib.sha256(recovery_code.encode()).hexdigest()
        salt,digest,rounds,recovery_digest,recovery=self._new_credential(new_password)
        with self.tx() as c:
            # The random recovery secret is the alternative when login is locked.
            row=c.execute('SELECT p.* FROM password_credentials p JOIN users u ON u.id=p.user_id WHERE u.phone=?',(phone,)).fetchone()
            if not row or not secrets.compare_digest(row['recovery_digest'],candidate):self._failed_auth(c,phone)
            c.execute('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',(salt,digest,rounds,recovery_digest,row['user_id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
            c.execute('DELETE FROM auth_attempts WHERE phone=?',(phone,))
        return {'ok':True,'recovery_code':recovery}
    def bootstrap_admin(self,phone,password):
        """Operator-only startup/CLI operation. Never exposed by an HTTP route."""
        self._trial_only();phone=self._phone(phone);self._password(password)
        salt,digest,rounds,recovery_digest,_=self._new_credential(password)
        with self.tx() as c:
            existing=c.execute('SELECT * FROM users WHERE phone=?',(phone,)).fetchone()
            if existing:
                self.require(existing['role'] in ('admin','developer'),'不能把已注册普通账号自动升级为管理员；请使用独立管理号码',409)
                return self.profile(existing['id'])
            uid=c.execute("INSERT INTO users(phone,nickname,role,college) VALUES(?,'转角客服','admin','计算机工程学院')",(phone,)).lastrowid
            c.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',(uid,salt,digest,rounds,recovery_digest))
        return self.profile(uid)

    def request_code(self,phone):
        self.require(not self.trial,'学院试用采用密码登录，测试验证码已关闭',403)
        self.require(isinstance(phone,str) and re.fullmatch(r'1[3-9]\d{9}',phone),'请输入11位手机号')
        code=str(secrets.randbelow(900000)+100000)
        with self.tx() as c:c.execute('INSERT OR REPLACE INTO otp VALUES(?,?,?,0)',(phone,hashlib.sha256(code.encode()).hexdigest(),time.time()+300))
        return {'demo_code':code,'simulation':True,'message':'本地测试验证码，不会发送短信'}

    def login(self,phone,code):
        self.require(not self.trial,'学院试用采用密码登录，测试验证码已关闭',403)
        with self.tx() as c:
            r=c.execute('SELECT * FROM otp WHERE phone=?',(phone,)).fetchone()
            valid=r and r['expires']>time.time() and r['attempts']<5 and secrets.compare_digest(r['digest'],hashlib.sha256(str(code).encode()).hexdigest())
            if not valid:
                if r:c.execute('UPDATE otp SET attempts=attempts+1 WHERE phone=?',(phone,))
                c.commit();raise DomainError('验证码错误、过期或已使用',401)
            c.execute('DELETE FROM otp WHERE phone=?',(phone,))
            existing=c.execute('SELECT status FROM users WHERE phone=?',(phone,)).fetchone()
            self.require(not existing or existing['status']=='active',
                         self.status_message(existing['status']) if existing else '',403)
            c.execute('INSERT OR IGNORE INTO users(phone,nickname) VALUES(?,?)',(phone,'同学'+phone[-4:]))
            uid=c.execute('SELECT id FROM users WHERE phone=?',(phone,)).fetchone()[0]
            token=secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400*7))
            c.execute('UPDATE users SET last_login=? WHERE id=?',(time.time(),uid))
        return {'token':token,'user':self.profile(uid),'simulation':True}

    def user(self,token):
        r=self.row('SELECT s.user_id,u.status FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time()))
        self.require(r,'请先登录',401)
        self.require(r['status']=='active',self.status_message(r['status']),403)
        return r['user_id']

    def logout(self,token):
        with self.tx() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def deactivate(self,u):
        """用户主动注销账号。保留订单、工单、信誉等记录（数据可追溯），
        但账号立即下线、在售商品全部下架、之后不可再登录。
        有未完结订单或未结案工单时禁止注销，堵住「货不对版就注销跑路」这条路。"""
        with self.tx() as c:
            open_order=c.execute("SELECT 1 FROM orders WHERE (buyer_id=? OR seller_id=?) AND status NOT IN ('completed','cancelled','refunded','partial_refunded') LIMIT 1",(u,u)).fetchone()
            self.require(not open_order,'还有未完成的订单，请先处理或申请售后后再注销')
            open_ticket=c.execute("""SELECT 1 FROM tickets t LEFT JOIN orders o ON o.id=t.order_id
                WHERE t.status NOT IN ('resolved','rejected')
                  AND (t.user_id=? OR o.buyer_id=? OR o.seller_id=?) LIMIT 1""",(u,u,u)).fetchone()
            self.require(not open_ticket,'还有未结案的工单，请等待处理完成后再注销')
            c.execute("UPDATE users SET status='deactivated' WHERE id=?",(u,))
            c.execute('DELETE FROM sessions WHERE user_id=?',(u,))
            c.execute("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'",(u,))
        return {'ok':True}

    def profile(self,u):
        r=self.row('SELECT id,nickname,college,major,education,bio,role,score,status FROM users WHERE id=?',(u,))
        self.require(r,'用户不存在',404);r.update(self.credit_badge(u,r['score']));return r

    def credit_badge(self,u,score=None):
        """信誉星级（不落库）：有效好评 = 买家给卖家的 4-5 星；严重违规 = 单次扣分 ≥15；
        星级调整 = 管理员通过 audit(type='stars') 累积的人为调整。"""
        if score is None:
            row=self.row('SELECT score FROM users WHERE id=?',(u,));score=row['score'] if row else 100
        good=self.row("SELECT COUNT(*) n FROM reviews r JOIN orders o ON o.id=r.order_id WHERE o.seller_id=? AND r.user_id=o.buyer_id AND r.rating>=4",(u,))['n']
        severe=self.row("SELECT COUNT(*) n FROM audit WHERE target=? AND type='credit' AND delta<=?",(u,-15))['n']
        adjust=self.row("SELECT COALESCE(SUM(delta),0) n FROM audit WHERE target=? AND type='stars'",(u,))['n']
        return star_badge(good,severe,score,adjust)

    def update_profile(self,u,d):
        nickname=self.text(d.get('nickname'),24,'昵称');college='计算机工程学院' if self.trial else str(d.get('college',''))[:80];major=str(d.get('major',''))[:80]
        education=d.get('education','本科');self.require(education in ['本科','专科','已毕业','其他'],'暂不开放该层次')
        with self.tx() as c:c.execute('UPDATE users SET nickname=?,college=?,major=?,education=?,bio=? WHERE id=?',(nickname,college,major,education,str(d.get('bio',''))[:300],u))
        return self.profile(u)

    def staff(self,u):self.require(self.is_staff(u),'仅客服、管理员或开发者可操作',403)
    def admin(self,u):
        """平台管理员闸门。用于「客服能做，但管理员才能担责」的那一类操作：
        人员授权、恢复上架、改判、动账。开发者拥有管理员的全部权限。"""
        self.require(self.is_admin(u),'仅平台管理员或开发者可操作',403)

    # --- 角色层级 ----------------------------------------------------------
    # 四级：user(0) < support(1) < admin(2) < developer(3)。
    # 开发者是最高权限：可任命/降级管理员；管理员可设/废客服、封号；
    # 客服日常值守；用户无后台权限。层级判断统一走这里，别在业务里手写比较。
    ROLE_RANK = {'user':0,'support':1,'admin':2,'developer':3}

    def role_of(self,u):
        # 直接查 role：profile 现在会附带信誉星级（两次统计查询），
        # 鉴权路径没必要为拿一个角色承担这份开销。
        r=self.row('SELECT role FROM users WHERE id=?',(u,));return r['role'] if r else ''
    def is_staff(self,u):return self.role_of(u) in ('support','admin','developer')
    def is_admin(self,u):return self.role_of(u) in ('admin','developer')

    def set_role_operator(self, phone, role):
        """本地 / 服务器操作者专用：直接设定任意账号角色。

        只用于引导「第一个开发者」——在此之前系统里没有开发者，
        而开发者权限要求又有开发者在场才能授予，必须由操作者在线下命令里破冰。
        不挂 HTTP 路由，永远走 manage_trial.py / 启动脚本。
        """
        self._trial_only()
        self.require(role in self.ROLE_RANK,'未知角色')
        phone=self._phone(phone)
        with self.tx() as c:
            row=c.execute('SELECT id,role FROM users WHERE phone=?',(phone,)).fetchone()
            self.require(row,'账号不存在',404)
            c.execute('UPDATE users SET role=? WHERE id=?',(role,row['id']))
            c.execute('INSERT INTO audit(target,type,reason,created) VALUES(?,?,?,?)',
                      (row['id'],'role_change',f'服务器操作者通过本地命令将角色调整为{role}',time.time()))
        return self.profile(row['id'])
