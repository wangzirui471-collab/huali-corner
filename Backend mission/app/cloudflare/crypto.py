"""密码与会话的异步实现。

为什么要重写
------------
现有 `account/service.py` 用 `hashlib.pbkdf2_hmac('sha256', ..., 600000)`。
在 Python Workers 实测 `hashlib.pbkdf2_hmac` 不存在（AttributeError），
`hashlib.scrypt` 同样不存在，`algorithms_available` 里只有 sha/md5/blake 系列。

所以派生必须交给运行时原生的 Web Crypto：`crypto.subtle.deriveBits`。
这是同算法（PBKDF2-HMAC-SHA256）、同轮数（600000）、同输出长度（32 字节）的
等价实现，不是降级。

算法契约必须与旧库完全一致，否则老用户无法登录：
    salt             secrets.token_hex(16)      -> 32 位十六进制
    digest           pbkdf2_hmac('sha256', password.encode('utf-8'),
                                 bytes.fromhex(salt), 600000).hex()
                     -> 64 位十六进制（32 字节）
    rounds           600000
    recovery_digest  sha256(recovery.encode()).hexdigest()
    session token    secrets.token_urlsafe(32)，入库只存 sha256(token).hexdigest()

不要减少轮数，不要改哈希，不要"为了跑得快"换成 sha256 单次。
"""
import hashlib
import secrets

from js import Object, Uint8Array, crypto
from pyodide.ffi import to_js

ROUNDS = 600000
KEY_BYTES = 32
SALT_HEX_LEN = 32
SESSION_TTL = 86400 * 7

__all__ = [
    'ROUNDS', 'SESSION_TTL', 'new_salt', 'derive', 'new_credential',
    'verify', 'new_session_token', 'session_digest', 'constant_time_equals',
]


def _js_object(mapping):
    return to_js(mapping, dict_converter=Object.fromEntries)


def constant_time_equals(left, right):
    """定长比较，不因提前返回泄露前缀匹配长度。

    不依赖 hmac 模块：在 Workers 里 hmac 的可用性未验证，自己实现更稳。
    """
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


async def derive(password, salt_hex, rounds=ROUNDS):
    """PBKDF2-HMAC-SHA256 -> 64 位十六进制摘要。"""
    if not isinstance(password, str):
        raise TypeError('password must be str')
    if rounds < 1:
        raise ValueError('rounds must be positive')

    parameters = _js_object({
        'name': 'PBKDF2',
        'salt': to_js(bytes.fromhex(salt_hex)),
        'iterations': rounds,
        'hash': 'SHA-256',
    })
    key = await crypto.subtle.importKey(
        'raw', to_js(password.encode('utf-8')),
        _js_object({'name': 'PBKDF2'}),
        False, to_js(['deriveBits']),
    )
    bits = await crypto.subtle.deriveBits(parameters, key, KEY_BYTES * 8)
    return bytes(Uint8Array.new(bits).to_py()).hex()


async def new_credential(password):
    """生成与旧表 password_credentials 完全兼容的一行。"""
    salt = new_salt()
    recovery = secrets.token_urlsafe(32)
    digest = await derive(password, salt)
    recovery_digest = hashlib.sha256(recovery.encode('utf-8')).hexdigest()
    return {
        'salt': salt,
        'digest': digest,
        'rounds': ROUNDS,
        'recovery_digest': recovery_digest,
        'recovery': recovery,
    }


async def verify(password, salt, digest, rounds=ROUNDS):
    """校验密码。即使账号不存在也要走完 KDF，避免通过耗时差异泄露账号是否存在。"""
    candidate = await derive(password, salt, rounds or ROUNDS)
    return constant_time_equals(candidate, digest)


def new_session_token():
    return secrets.token_urlsafe(32)


def session_digest(token):
    """会话表只存摘要，不存明文 token。"""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
