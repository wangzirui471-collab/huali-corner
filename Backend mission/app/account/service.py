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


class AccountService(ValidationMixin):

    def _trial_only(self):self.require(self.trial,'此接口仅供学院试用版使用',403)
    def _phone(self,phone):
        self.require(isinstance(phone,str) and re.fullmatch(r'1[3-9][0-9]{9}',phone),'请输入11位手机号')
        return phone
    def _password(self,password):
        self.require(isinstance(password,str) and 12<=len(password)<=128,'密码需为12至128个字符，不要使用其他网站的密码')
        return password
    @staticmethod
    def _derive(password,salt,rounds=ROUNDS):
        return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),rounds).hex()
    def _new_credential(self,password):
        salt=secrets.token_hex(16);recovery=secrets.token_urlsafe(32)
        return salt,self._derive(password,salt),ROUNDS,hashlib.sha256(recovery.encode()).hexdigest(),recovery
    def _session(self,c,uid):
        self.require(c.execute('SELECT is_active FROM users WHERE id=?',(uid,)).fetchone()['is_active'],'账号已停用，请联系运营者',403)
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
        self.require(False,'手机号、密码或恢复码不正确',401)
    def register_password(self,phone,password,nickname):
        self._trial_only();phone=self._phone(phone);self._password(password)
        nickname=self.text(nickname,24,'昵称');salt,digest,rounds,recovery_digest,recovery=self._new_credential(password)
        with self.tx() as c:
            self.require(not c.execute('SELECT 1 FROM users WHERE phone=?',(phone,)).fetchone(),'此手机号已注册，请登录或使用恢复码',409)
            uid=c.execute("INSERT INTO users(phone,nickname,college,role) VALUES(?,?,'计算机工程学院','user')",(phone,nickname)).lastrowid
            c.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',(uid,salt,digest,rounds,recovery_digest))
            token=self._session(c,uid)
        return self._trial_result(uid,token,recovery)
    def login_password(self,phone,password):
        self._trial_only();phone=self._phone(phone)
        self.require(isinstance(password,str) and len(password)<=128,'手机号、密码或恢复码不正确',401)
        with self.connect() as c:self._lock_check(c,phone)
        credential=self.row('SELECT p.* FROM password_credentials p JOIN users u ON u.id=p.user_id WHERE u.phone=?',(phone,))
        # Perform the KDF even for an unknown phone; do not disclose account existence.
        digest=self._derive(password,credential['salt'] if credential else '00'*16,credential['rounds'] if credential else ROUNDS)
        with self.tx() as c:
            self._lock_check(c,phone)
            current=c.execute('SELECT p.* FROM password_credentials p JOIN users u ON u.id=p.user_id WHERE u.phone=?',(phone,)).fetchone()
            if not current or not secrets.compare_digest(current['digest'],digest):self._failed_auth(c,phone)
            c.execute('DELETE FROM auth_attempts WHERE phone=?',(phone,));uid=current['user_id'];token=self._session(c,uid)
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
        self.require(isinstance(recovery_code,str) and len(recovery_code)<=128,'手机号、密码或恢复码不正确',401)
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
                self.require(existing['role']=='admin','不能把已注册普通账号自动升级为管理员；请使用独立管理号码',409)
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
            c.execute('INSERT OR IGNORE INTO users(phone,nickname) VALUES(?,?)',(phone,'同学'+phone[-4:]))
            uid=c.execute('SELECT id FROM users WHERE phone=?',(phone,)).fetchone()[0]
            token=secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400*7))
        return {'token':token,'user':self.profile(uid),'simulation':True}

    def user(self,token):
        r=self.row('SELECT s.user_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.is_active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time()))
        self.require(r,'请先登录',401);return r['user_id']

    def logout(self,token):
        with self.tx() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def profile(self,u):
        r=self.row('SELECT id,nickname,college,major,education,bio,role,score FROM users WHERE id=?',(u,))
        self.require(r,'用户不存在',404);return r

    def update_profile(self,u,d):
        nickname=self.text(d.get('nickname'),24,'昵称');college='计算机工程学院' if self.trial else str(d.get('college',''))[:80];major=str(d.get('major',''))[:80]
        education=d.get('education','本科');self.require(education in ['本科','专科','已毕业','其他'],'暂不开放该层次')
        with self.tx() as c:c.execute('UPDATE users SET nickname=?,college=?,major=?,education=?,bio=? WHERE id=?',(nickname,college,major,education,str(d.get('bio',''))[:300],u))
        return self.profile(u)

    def staff(self,u):self.require(self.profile(u)['role'] in ['admin','support'],'仅客服或管理员可操作',403)
