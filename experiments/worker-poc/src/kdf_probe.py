"""Synthetic vector for the legacy 600000-round PBKDF2-HMAC-SHA256 format.

This mirrors the existing pure-Python Worker algorithm for platform measurement.
It handles one 32-byte PBKDF2 block and is not a new credential protocol.
"""

import hashlib


def derive(password: str, salt_hex: str, rounds: int = 600000) -> str:
    """按旧格式派生 32 字节密码摘要，仅用于合成向量和平台耗时验证。

    password 为合成明文，salt_hex 为十六进制盐，返回十六进制摘要。
    不降低 600000 轮强度，也不用于接收真实用户凭据。
    """
    key = password.encode("utf-8")
    salt = bytes.fromhex(salt_hex)
    if len(key) > 64:
        key = hashlib.sha256(key).digest()
    padded = key + b"\x00" * (64 - len(key))
    inner = hashlib.sha256(bytes(byte ^ 0x36 for byte in padded))
    outer = hashlib.sha256(bytes(byte ^ 0x5C for byte in padded))
    digest = inner.copy()
    digest.update(salt + (1).to_bytes(4, "big"))
    value = digest.digest()
    finish = outer.copy()
    finish.update(value)
    value = finish.digest()
    total = int.from_bytes(value, "big")
    for _ in range(rounds - 1):
        digest = inner.copy()
        digest.update(value)
        value = digest.digest()
        finish = outer.copy()
        finish.update(value)
        value = finish.digest()
        total ^= int.from_bytes(value, "big")
    return total.to_bytes(32, "big").hex()
