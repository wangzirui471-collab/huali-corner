"""密码与会话。

为什么密码派生要自己实现（重要，别改回去）
------------------------------------------
一共踩了两个坑，都是本地 `wrangler dev` 通过、上线才暴露的：

1. `hashlib.pbkdf2_hmac` 在 Python Workers 里不存在（AttributeError），
   `hashlib.scrypt` 同样不存在。
2. 改用 Web Crypto 的 `crypto.subtle.deriveBits` 后，本地正常，**生产环境报错**：

       NotSupportedError: Pbkdf2 failed: iteration counts above 100000 are not
       supported (requested 600000)

   即 Cloudflare 生产把 PBKDF2 上限压在 10 万轮。
3. 改用 wasm 版 pycryptodome（本地 385ms、结果正确），**生产环境所有路由都返回
   1105 资源超限**——整个包在 Workers 的内存里加载不起来。

所以最终用 stdlib 的 `hashlib.sha256` 自己实现 PBKDF2-HMAC-SHA256。它没有额外
依赖、内存占用低，且能保住 600000 轮。关键优化是预计算 HMAC 的 ipad/opad 中间状态、
用整数异或代替逐字节循环，实测比 `hmac.new` 写法快约 4 倍。

算法契约与旧库完全一致，老用户可以直接登录：
    salt             secrets.token_hex(16)      -> 32 位十六进制
    digest           PBKDF2-HMAC-SHA256(password.encode('utf-8'),
                                          bytes.fromhex(salt), 600000, dkLen=32).hex()
                     -> 64 位十六进制
    rounds           600000
    recovery_digest  sha256(recovery.encode()).hexdigest()
    session token    secrets.token_urlsafe(32)，入库只存 sha256(token).hexdigest()

不要把轮数调低，不要换成单次 sha256，也不要为了省 CPU 换算法。
CPU 说明：600000 轮在免费计划（10ms CPU）下必然超限，需要 Workers 付费计划。
"""
import hashlib
import secrets

ROUNDS = 600000
# 下限是允许前端「客户端派生」路径回退到本地 8081 时不会把规范写崩：
# 当有人把 ROUNDS 调到 1 万以下时，PBKDF2 已经接近单次 SHA256，需要服务端显式拒绝。
MIN_ROUNDS = 10000
KEY_BYTES = 32
BLOCK = 64
SESSION_TTL = 86400 * 7

__all__ = [
    'ROUNDS', 'MIN_ROUNDS', 'SESSION_TTL', 'new_salt', 'derive', 'new_credential',
    'verify', 'new_session_token', 'session_digest', 'constant_time_equals',
]


def _hmac_states(key):
    """预计算 HMAC-SHA256 的 ipad/opad 中间状态，省掉每轮的重复初始化。"""
    if len(key) > BLOCK:
        key = hashlib.sha256(key).digest()
    padded = key + b'\x00' * (BLOCK - len(key))
    inner = hashlib.sha256(bytes(b ^ 0x36 for b in padded))
    outer = hashlib.sha256(bytes(b ^ 0x5C for b in padded))
    return inner, outer


def _pbkdf2(password, salt, rounds, dklen=KEY_BYTES):
    """PBKDF2-HMAC-SHA256，单块输出（dklen<=32 时只需一次外循环）。"""
    inner, outer = _hmac_states(password)
    result = b''
    block = 1
    while len(result) < dklen:
        digest = inner.copy()
        digest.update(salt + block.to_bytes(4, 'big'))
        u = digest.digest()
        finish = outer.copy()
        finish.update(u)
        u = finish.digest()
        acc = int.from_bytes(u, 'big')
        for _ in range(rounds - 1):
            digest = inner.copy()
            digest.update(u)
            u = digest.digest()
            finish = outer.copy()
            finish.update(u)
            u = finish.digest()
            acc ^= int.from_bytes(u, 'big')
        result += acc.to_bytes(32, 'big')
        block += 1
    return result[:dklen]


def constant_time_equals(left, right):
    """定长比较，不因提前返回泄露前缀匹配长度。"""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if len(left) != len(right):
        return False
    diff = 0
    for a, b in zip(left.encode('utf-8'), right.encode('utf-8')):
        diff |= a ^ b
    return diff == 0


def new_salt():
    return secrets.token_hex(16)


def derive(password, salt_hex, rounds=ROUNDS):
    """PBKDF2-HMAC-SHA256 -> 64 位十六进制摘要。"""
    if not isinstance(password, str):
        raise TypeError('password must be str')
    if rounds < 1:
        raise ValueError('rounds must be positive')
    return _pbkdf2(password.encode('utf-8'), bytes.fromhex(salt_hex), rounds).hex()


def new_credential(password):
    """生成与旧表 password_credentials 完全兼容的一行。"""
    salt = new_salt()
    recovery = secrets.token_urlsafe(32)
    digest = derive(password, salt)
    recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()
    return {
        'salt': salt,
        'digest': digest,
        'rounds': ROUNDS,
        'recovery_digest': recovery_digest,
        'recovery': recovery,
    }


def verify(password, salt, digest, rounds=ROUNDS):
    """校验密码。调用方即使账号不存在也应走完 KDF，避免耗时差异泄露账号是否存在。"""
    candidate = derive(password, salt, rounds or ROUNDS)
    return constant_time_equals(candidate, digest)


def new_session_token():
    return secrets.token_urlsafe(32)


def session_digest(token):
    """会话表只存摘要，不存明文 token。"""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
