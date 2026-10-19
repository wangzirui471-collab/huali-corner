"""Async Cloudflare adapters for the existing trial application.

Routes retain local domain contracts, role checks and simulated trade rules.
D1/R2 are accessed through bindings; no production fixture writes occur here.
"""
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlsplit

from workers import Response

from ..core.errors import DomainError
from . import crypto, sessions
from .d1 import DB_LIMIT_BYTES, Database
from .http import (
    ApiError, error_response, guard, int_param, json_body, json_response,
    path_of, query_of, require,
)
from .media import MediaStore

# 与 account/service.py 保持一致的账号规则
PHONE_RE = r'1[3-9][0-9]{9}'
SESSION_TTL = crypto.SESSION_TTL

BUILDINGS = [
    '本科综合楼', '行政楼', '7号楼仓库', 'A1', 'A2', 'A3', 'A4', 'B1', 'B2', 'B3', 'B4', 'B9',
    'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'D1', 'D2', 'D5', 'D6', 'G1主楼',
    'G1副楼', 'G2', 'G3', 'G4主楼', 'G4副楼', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7',
    'L8', 'L9', 'L10', 'L11', 'L12', 'L13', 'L15', 'L16', 'L17', 'L18',
]

STATUS_MESSAGES = {
    'banned': '该账号已被封禁，如有异议可在客服中心申诉',
    'deactivated': '该账号已注销',
    'disabled': '该账号已被平台停用，请联系管理员',
    'deleted': '该账号已被清除，请用原手机号重新注册',
}


from .read_pages import ReadPages
from .rules_adapter import CloudRules
from .trade_api import TradeApi, TRADE_ROUTES
from .catalog_api import CatalogApi, CATALOG_ROUTES
from .community_api import CommunityApi, COMMUNITY_ROUTES
from .staff_api import StaffApi, STAFF_ROUTES
from .auth_api import AuthApi, AUTH_ROUTES


class Api(AuthApi, StaffApi, CatalogApi, CommunityApi, TradeApi, CloudRules, ReadPages):
    def __init__(self, env):
        self.env = env
        self.db = Database(env.DB)
        self.media_store = MediaStore(env.MEDIA)
        self.assets = getattr(env, 'ASSETS', None)

    # ---- 账号辅助 --------------------------------------------------------

    async def require_capacity(self):
        """写路径统一前置检查：库到达 10GB 上限前给出可读错误。

        每个新增数据的入口（注册、发布、下单……）在写库前调用一次；
        查询本身是 `SELECT 1`，开销可忽略。取不到大小时不拦，由平台
        硬限制兜底，宁可漏拦也不误拦。
        """
        used = await self.db.used_bytes()
        if used is not None and used >= DB_LIMIT_BYTES:
            raise ApiError('数据库已达容量上限，暂停新数据写入，请联系管理员', 507)

    @staticmethod
    def normalize_account(raw):
        """11 位手机号，或邮箱（统一小写）。与旧实现同规则。"""
        require(isinstance(raw, str), '请输入11位手机号或邮箱')
        value = raw.strip()
        if '@' in value:
            require(len(value) <= 120 and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value),
                    '请输入11位手机号或邮箱')
            return value.lower()
        require(re.fullmatch(PHONE_RE, value), '请输入11位手机号或邮箱')
        return value

    @staticmethod
    def check_password(password):
        require(isinstance(password, str) and 6 <= len(password) <= 128,
                '密码需为6至128个字符，不要使用其他网站的密码')
        return password

    @staticmethod
    def check_digest(digest):
        """客户端 PBKDF2 上传的 32 字节十六进制摘要。"""
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest or ''),
                '提交的口令摘要格式不正确', 400)
        return digest

    @staticmethod
    def check_salt(salt):
        """16 字节十六进制盐。"""
        require(isinstance(salt, str) and re.fullmatch(r'[0-9a-f]{32}', salt or ''),
                '提交的盐格式不正确', 400)
        return salt

    @staticmethod
    def check_rounds(rounds):
        """New credentials always use the configured 600000-round KDF."""
        require(type(rounds) is int and rounds == crypto.ROUNDS,
                f'新凭据轮数须为 {crypto.ROUNDS}', 400)
        return rounds

    async def profile_dto(self, user_id):
        row = await self.db.first(
            '''SELECT id,nickname,college,major,education,bio,role,score,status,
                      degree_level,study_status,profile_version,avatar_upload_id
               FROM users WHERE id=?''', (user_id,))
        if not row:
            raise ApiError('请先登录', 401)
        avatar_url = None
        avatar_id = row['avatar_upload_id']
        if avatar_id:
            owned = await self.db.first(
                'SELECT upload_id FROM user_avatar_uploads WHERE upload_id=? AND user_id=?',
                (avatar_id, user_id))
            if owned:
                avatar_url = '/media/' + avatar_id
        dto = {
            'id': row['id'],
            'nickname': row['nickname'],
            'college': row['college'],
            'major': row['major'],
            'education': row['education'],
            'bio': row['bio'],
            'role': row['role'],
            'score': row['score'],
            'degree_level': row['degree_level'],
            'study_status': row['study_status'],
            'profile_version': row['profile_version'],
            'avatar_upload_id': avatar_id if avatar_url else None,
            'avatar_url': avatar_url,
            'status': row['status'],
        }
        dto.update(await self.star_badge(user_id, dto['score']))
        return dto

    async def star_badge(self, user_id, score):
        from ..account.credit import star_badge

        good = await self.db.scalar(
            '''SELECT COUNT(*) FROM reviews r JOIN orders o ON o.id=r.order_id
               WHERE o.seller_id=? AND r.user_id=o.buyer_id AND r.rating>=4''', (user_id,))
        severe = await self.db.scalar(
            "SELECT COUNT(*) FROM audit WHERE target=? AND type='credit' AND delta<=?",
            (user_id, -15))
        adjust = await self.db.scalar(
            "SELECT COALESCE(SUM(delta),0) FROM audit WHERE target=? AND type='stars'",
            (user_id,))
        return star_badge(good or 0, severe or 0, score, adjust or 0)

    async def trusted_map(self, seller_ids):
        from ..account.credit import is_trusted

        ids = sorted({int(x) for x in seller_ids if x})
        if not ids:
            return {}
        marks = ','.join('?' * len(ids))
        stats = {i: {'listings': 0, 'delivered': 0, 'late': 0, 'refunded': 0} for i in ids}
        for row in await self.db.all(
                f'SELECT seller_id,COUNT(*) n FROM products WHERE seller_id IN ({marks}) GROUP BY seller_id',
                tuple(ids)):
            stats[row['seller_id']]['listings'] = row['n']
        for row in await self.db.all(
            'SELECT seller_id,'
            " SUM(CASE WHEN delivered_at IS NOT NULL OR handover_at IS NOT NULL"
            " OR status IN ('awaiting_receipt','completed','refunded','partial_refunded') THEN 1 ELSE 0 END) delivered,"
            " SUM(CASE WHEN delivered_at IS NOT NULL AND appointment>0 AND delivered_at>appointment THEN 1 ELSE 0 END) late,"
            " SUM(CASE WHEN status IN ('refunded','partial_refunded') THEN 1 ELSE 0 END) refunded"
            f' FROM orders WHERE seller_id IN ({marks}) GROUP BY seller_id', tuple(ids)):
            stats[row['seller_id']].update(
                delivered=row['delivered'] or 0,
                late=row['late'] or 0,
                refunded=row['refunded'] or 0)
        inactive = {r['id'] for r in await self.db.all(
            f"SELECT id FROM users WHERE id IN ({marks}) AND status<>'active'", tuple(ids))}
        return {i: (i not in inactive) and is_trusted(**v) for i, v in stats.items()}

    # ---- 配置 ------------------------------------------------------------

    async def config(self, request):
        # 字段与 server.py 的 /api/config 完全一致，前端不需要改。
        # auth_mode:
        #   'password'   — 后端用 hashlib.pbkdf2_hmac 派生，仅本地 8081 可用（CPython 快）；
        #   'client_kdf' — 浏览器先 PBKDF2-HMAC-SHA256 算出 digest 再提交，
        #                  让 Workers 免费计划 10ms CPU 也能扛 600000 轮；
        #                  服务端不再算 digest，只做定长比较和会话签发。
        #   'demo'       — 公开演示版，无登录态。
        # 何时回退：
        #   - 浏览器 SubtleCrypto 出错或不支持大迭代数时，前端兜底走本地静态演示；
        #   - 部署者把 ROUNDS 调到 1 万以下时，前端拒绝继续派生并提示。
        return json_response({
            'simulation': True,
            'trial': True,
            'auth_mode': 'client_kdf',
            'pbkdf2_rounds': crypto.ROUNDS,
            'phone_verified': False,
            'name': '华立转角',
            'pilot': '计算机工程学院',
            'campus': '广州校区',
            'support_hours': '08:00–20:00',
            'colleges': [{'source_name': '计算机工程学院'}],
            'buildings': BUILDINGS,
        })

    # ---- 商品 ------------------------------------------------------------

    async def products(self, request):
        query = query_of(request)
        uid, _ = await sessions.current_user_id(self.db, request)

        page = max(1, int(query.get('page') or 1))
        limit = max(0, int(query.get('limit') or 0))
        where = ["p.status='available'"]
        args = []
        if query.get('seller'):
            where.append('p.seller_id=?')
            args.append(int(query['seller']))
        if query.get('category'):
            where.append('p.category=?')
            args.append(query['category'])

        rows = await self.db.all(
            'SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p '
            'JOIN users u ON u.id=p.seller_id WHERE ' + ' AND '.join(where) +
            ' ORDER BY p.id DESC', tuple(args))

        base = []
        for row in rows:
            detail = json.loads(row['data'] or '{}')
            detail.pop('proof', None)
            moderation = detail.pop('moderation', None)
            item = dict(row)
            item.pop('data', None)
            item.update(detail)
            item['under_review'] = bool(moderation and not moderation.get('reviewed'))
            base.append(item)

        if query.get('favorite'):
            require(uid is not None, '请先登录', 401)
            favorites = {r['product_id'] for r in await self.db.all(
                "SELECT product_id FROM reactions WHERE user_id=? AND kind='favorite'", (uid,))}
            base = [p for p in base if p['id'] in favorites]

        words = str(query.get('q') or '').lower().split()
        if words:
            keys = ['title', 'description', 'isbn', 'publisher', 'major', 'edition']
            base = [p for p in base
                    if all(w in ' '.join(str(p.get(k, '')) for k in keys).lower() for w in words)]

        if query.get('sort') == 'price':
            base.sort(key=lambda p: p['price'] + (p['delivery_fee'] if p['delivery'] == 'delivery' else 0))
        now = time.time()
        base.sort(key=lambda p: 0 if (p.get('promoted_until') or 0) > now else 1)

        items = base[(page - 1) * limit:page * limit] if limit else base
        trusted = await self.trusted_map([p['seller_id'] for p in items])
        for item in items:
            item['seller_trusted'] = trusted.get(item['seller_id'], False)
            item['likes'] = await self.db.scalar(
                "SELECT COUNT(*) FROM reactions WHERE product_id=? AND kind='like'", (item['id'],)) or 0
            item['liked'] = bool(uid and await self.db.first(
                "SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='like'",
                (item['id'], uid)))
            item['favorited'] = bool(uid and await self.db.first(
                "SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='favorite'",
                (item['id'], uid)))
        return json_response(items)

    async def product(self, request):
        pid = int_param(query_of(request), 'id')
        row = await self.db.first(
            'SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p '
            'JOIN users u ON u.id=p.seller_id WHERE p.id=?', (pid,))
        require(row is not None, '商品不存在', 404)
        detail = json.loads(row['data'] or '{}')
        detail.pop('proof', None)
        moderation = detail.pop('moderation', None)
        item = dict(row)
        item.pop('data', None)
        item.update(detail)
        item['under_review'] = bool(moderation and not moderation.get('reviewed'))
        return json_response(item)

    # ---- 认证 ------------------------------------------------------------

    async def register(self, request):
        """注册。

        在 Workers 试用版上客户端已经做完 600000 轮 PBKDF2，服务端只验
        收 `{phone, nickname, salt, rounds, digest}`、把 digest 直接落库。
        这避免了 Workers 免费计划 10ms CPU 上跑不动 600k 轮的问题（实
        测 Python 派生 ~660ms，必然触发 1102/超时）。600k 轮的强度仍在
        客户端保留；服务端不做任何派生。

        安全权衡（重要）：digest 落库后，D1 一旦泄漏，攻击者拿到的是
        已派生好的摘要，可以直接拿来做「pass-the-hash」登录，不再需要
        爆破明文。600k 轮原本能让爆破时间从「秒级」抬到「数年」，但前
        提是攻击者拿不到摘要。把摘要直接落库就是把这一前提让出去了——
        这是为了不在付费计划之前下线试用而做的妥协，等切到 Workers
        Paid 或自有 KDF 服务时要立刻改回服务端派生，并在提交中说明。
        """
        await self.require_capacity()
        data = await json_body(request)
        account = self.normalize_account(data.get('phone'))
        nickname = (data.get('nickname') or '').strip()
        require(0 < len(nickname) <= 24, '昵称需填写且不超过24字')
        salt = self.check_salt(data.get('salt'))
        rounds = self.check_rounds(int(data.get('rounds') or 0))
        digest = self.check_digest(data.get('digest'))

        exists = await self.db.first('SELECT 1 FROM users WHERE phone=?', (account,))
        require(not exists, '此账号已注册，请登录或使用恢复码', 409)

        # 服务端仍生成恢复码 + 摘要：恢复码不上 KDF，明文生成后存哈希。
        recovery = secrets.token_urlsafe(32)
        recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()

        # 用户与密码必须一次成事：第二条语句用子查询自取 id，不依赖交互式事务。
        results = await self.db.batch([
            ('INSERT INTO users(phone,nickname,college,role) VALUES(?,?,?,?)',
             (account, nickname, '计算机工程学院', 'user')),
            ('''INSERT INTO password_credentials(user_id,salt,digest,rounds,recovery_digest)
                SELECT id,?,?,?,? FROM users WHERE phone=?''',
             (salt, digest, rounds, recovery_digest, account)),
        ])
        self.db.expect(results[0], '注册失败，请重试')
        self.db.expect(results[1], '注册失败，请重试')

        user_id = await self.db.scalar('SELECT id FROM users WHERE phone=?', (account,))
        token = crypto.new_session_token()
        await sessions.issue_session(self.db, user_id, token, SESSION_TTL)
        return json_response({
            'token': token,
            'user': await self.profile_dto(user_id),
            'simulation': True,
            'phone_verified': False,
            'recovery_code': recovery,
        })

    async def auth_salt(self, request):
        """返回某账号的 (salt, rounds) 供浏览器做客户端 PBKDF2。

        为了不增加额外 D1 读（避免给攻击者「账号不存在」的强信号），
        这里对未注册的账号也回 200，盐和轮数填一份固定占位，调用方
        算出来的 digest 自然和服务端对不上 → 后续 `/api/auth/login`
        仍然 401。这与原 `/api/auth/login` 在「账号不存在」时也走完
        KDF 的策略一致。

        但要承认的是：响应里的 salt 是真实盐还是占位，本身就泄露了
        账号是否存在——这条路径比同步派生更难做到严格恒时。在校园试
        用里这是可接受的；如果要严格无侧信道，需要把这份信息也下放
        到 cookie 或预签发 token 里。
        """
        query = query_of(request)
        raw = query.get('phone') or ''
        require(isinstance(raw, str) and raw.strip(), '请输入11位手机号或邮箱', 400)
        account = self.normalize_account(raw)
        row = await self.db.first(
            '''SELECT p.salt,p.rounds FROM password_credentials p
               JOIN users u ON u.id=p.user_id WHERE u.phone=?''', (account,))
        if row:
            return json_response({'salt': row['salt'], 'rounds': int(row['rounds'])})
        return json_response({'salt': '00' * 16, 'rounds': crypto.ROUNDS})

    async def login(self, request):
        """登录：客户端已经用 `/api/auth/salt` 拿到的 salt+rounds 派生好 digest。

        服务端只做：定长比较 digest、清尝试计数、签发会话 token。
        """
        data = await json_body(request)
        account = self.normalize_account(data.get('phone'))
        digest = self.check_digest(data.get('digest'))

        attempt = await self.db.first('SELECT attempts,reset_at FROM auth_attempts WHERE phone=?', (account,))
        if attempt and float(attempt['reset_at']) > time.time() and attempt['attempts'] >= 5:
            raise ApiError('尝试次数过多，请15分钟后重试或使用恢复码', 429)

        row = await self.db.first(
            '''SELECT p.digest,p.recovery_digest,u.id user_id,u.status
               FROM password_credentials p JOIN users u ON u.id=p.user_id
               WHERE u.phone=?''', (account,))
        # 账号不存在也要做一次定长比较，避免 digest 比较的耗时差异泄露账号是否存在。
        stored = row['digest'] if row else '0' * 64
        matched = row is not None and crypto.constant_time_equals(digest, stored)

        if not matched:
            now = time.time()
            fresh = attempt and float(attempt['reset_at']) > now
            count = (attempt['attempts'] + 1) if fresh else 1
            reset_at = attempt['reset_at'] if fresh else now + 900
            await self.db.run('INSERT OR REPLACE INTO auth_attempts(phone,attempts,reset_at) VALUES(?,?,?)',
                              (account, count, reset_at))
            raise ApiError('账号、密码或恢复码不正确', 401)

        if row['status'] != 'active':
            raise ApiError(STATUS_MESSAGES.get(row['status'], '账号状态异常，请联系管理员'), 403)

        token = crypto.new_session_token()
        await self.db.batch([
            ('DELETE FROM auth_attempts WHERE phone=?', (account,)),
            ('INSERT OR REPLACE INTO sessions(token,user_id,expires) VALUES(?,?,?)',
             (crypto.session_digest(token), row['user_id'], time.time() + SESSION_TTL)),
            ('UPDATE users SET last_login=? WHERE id=?', (time.time(), row['user_id'])),
        ])
        return json_response({
            'token': token,
            'user': await self.profile_dto(row['user_id']),
            'simulation': True,
            'phone_verified': False,
        })

    async def recover(self, request):
        """用恢复码重置密码：客户端已经派生好新 digest，服务端验证恢复码后落库。"""
        data = await json_body(request)
        account = self.normalize_account(data.get('phone'))
        recovery_code = data.get('recovery_code')
        require(isinstance(recovery_code, str) and 0 < len(recovery_code) <= 128,
                '账号、密码或恢复码不正确', 401)
        salt = self.check_salt(data.get('salt'))
        rounds = self.check_rounds(int(data.get('rounds') or 0))
        digest = self.check_digest(data.get('digest'))

        row = await self.db.first(
            '''SELECT p.recovery_digest,u.id user_id
               FROM password_credentials p JOIN users u ON u.id=p.user_id
               WHERE u.phone=?''', (account,))
        if not row or not crypto.constant_time_equals(
                hashlib.sha256(recovery_code.encode('utf-8')).hexdigest(),
                row['recovery_digest']):
            raise ApiError('账号、密码或恢复码不正确', 401)

        recovery = secrets.token_urlsafe(32)
        recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()
        results = await self.db.batch([
            ('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',
             (salt, digest, rounds, recovery_digest, row['user_id'])),
            ('DELETE FROM sessions WHERE user_id=?', (row['user_id'],)),
            ('DELETE FROM auth_attempts WHERE phone=?', (account,)),
        ])
        self.db.expect(results[0], '重置失败，请重试')
        return json_response({'ok': True, 'recovery_code': recovery})

    async def change_password(self, request):
        """已登录用户改密码：客户端分别派生老 digest 与新 digest，服务端比对后落库。"""
        uid = await sessions.require_user_id(self.db, request)
        data = await json_body(request)
        old_digest = self.check_digest(data.get('old_digest'))
        salt = self.check_salt(data.get('salt'))
        rounds = self.check_rounds(int(data.get('rounds') or 0))
        digest = self.check_digest(data.get('digest'))

        row = await self.db.first('SELECT digest FROM password_credentials WHERE user_id=?', (uid,))
        if not row or not crypto.constant_time_equals(old_digest, row['digest']):
            raise ApiError('原密码不正确', 401)

        recovery = secrets.token_urlsafe(32)
        recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()
        results = await self.db.batch([
            ('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',
             (salt, digest, rounds, recovery_digest, uid)),
            ('DELETE FROM sessions WHERE user_id=?', (uid,)),
            ('DELETE FROM auth_attempts WHERE phone=(SELECT phone FROM users WHERE id=?)', (uid,)),
        ])
        self.db.expect(results[0], '修改失败，请重试')
        return json_response({'ok': True, 'recovery_code': recovery})

    async def logout(self, request):
        await sessions.revoke_session(self.db, request)
        return json_response({'ok': True})

    async def me(self, request):
        uid = await sessions.require_user_id(self.db, request)
        return json_response(await self.profile_dto(uid))

    # ---- 媒体 ------------------------------------------------------------

    async def media(self, request, key):
        """Private history is owner-only; selected active avatars are public."""
        uid, status = await sessions.current_user_id(self.db, request)
        active = uid is not None and status == 'active'
        cache = 'private, no-store'
        if key.startswith('ua_'):
            # Avatars use a separate registry; staff have no preview bypass.
            from ..account.avatars import AVATAR_ID
            require(AVATAR_ID.fullmatch(key), '图片不存在', 404)
            row = await self.db.first(
                'SELECT a.*,u.status owner_status,u.avatar_upload_id FROM user_avatar_uploads a '
                'JOIN users u ON u.id=a.user_id WHERE a.upload_id=?', (key,))
            require(row is not None, '图片不存在', 404)
            selected = row['owner_status'] == 'active' and row['avatar_upload_id'] == key
            owner = active and uid == row['user_id']
            require(selected or owner, '无权读取此头像', 403)
            path = row['path']
        else:
            upload = await self.db.first('SELECT * FROM uploads WHERE id=?', (key,))
            require(upload is not None, '图片不存在', 404)
            if upload['private']:
                role = None
                if active:
                    role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
                require(active and (uid == upload['user_id'] or role in ('admin', 'support', 'developer')),
                        '无权读取私密图片', 403)
            else:
                needle = '%/media/' + key + '%'
                listed = await self.db.first(
                    "SELECT 1 FROM products WHERE status<>'removed' AND data LIKE ?", (needle,))
                if not listed:
                    listed = await self.db.first('SELECT 1 FROM orders WHERE items LIKE ?', (needle,))
                require(listed or (active and uid == upload['user_id']), '图片尚未发布', 403)
                if listed:
                    cache = 'public, max-age=3600'
            path = upload['path']
        body, content_type = await self.media_store.read(path)
        return Response(body, headers={'Content-Type': content_type,
                                       'Cache-Control': cache,
                                       'X-Content-Type-Options': 'nosniff',
                                       'Vary': 'Authorization'})

    # ---- 分发 ------------------------------------------------------------

    async def dispatch(self, request):
        path = path_of(request)
        method = request.method.upper()

        if path.startswith('/media/'):
            return await self.media(request, path[len('/media/'):])

        route = ROUTES.get(path)
        if route is None:
            if path.startswith('/api/'):
                return error_response('该接口尚未在试用版开放', 501)
            # 静态资源与 SPA 回退交给 Assets 绑定处理，不在 Python 里读文件。
            if self.assets is not None:
                return await self.assets.fetch(request)
            return error_response('页面不存在', 404)

        allowed, handler = route
        if method not in allowed:
            return error_response('请求方法不被允许', 405)
        return await getattr(self, handler)(request)


ROUTES = {
    '/api/health': (('GET',), 'health'),
    '/api/my-products': (('GET',), 'my_products'),
    '/api/orders': (('GET',), 'orders'),
    '/api/offers': (('GET',), 'offers'),
    '/api/notifications': (('GET', 'POST'), 'notifications'),
    '/api/badges': (('GET',), 'badges'),
    '/api/profile': (('GET',), 'public_profile'),
    '/api/user/profile': (('GET',), 'user_profile'),
    '/api/tickets': (('GET',), 'tickets'),
    '/api/admin': (('GET',), 'admin_overview'),
    '/api/audit': (('GET',), 'audit'),
    '/api/product/removed': (('GET',), 'removed_products'),
    '/api/admin/content': (('GET',), 'flagged_content'),
    '/api/reconcile': (('GET',), 'reconcile'),
    '/api/config': (('GET',), 'config'),
    '/api/products': (('GET',), 'products'),
    '/api/product': (('GET',), 'product'),
    '/api/auth/salt': (('GET',), 'auth_salt'),
    '/api/auth/register': (('POST',), 'register'),
    '/api/auth/login': (('POST',), 'login'),
    '/api/auth/recover': (('POST',), 'recover'),
    '/api/auth/logout': (('POST',), 'logout'),
    '/api/auth/password': (('POST',), 'change_password'),
    '/api/me': (('GET',), 'me'),
}

ROUTES.update(TRADE_ROUTES)
ROUTES.update(CATALOG_ROUTES)
ROUTES.update(COMMUNITY_ROUTES)
ROUTES.update(STAFF_ROUTES)
ROUTES.update(AUTH_ROUTES)
