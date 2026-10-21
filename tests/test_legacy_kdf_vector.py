"""Synthetic vector that a replacement Worker KDF must preserve."""

from pathlib import Path
import hashlib
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backend mission"))
from app.cloudflare.crypto import ROUNDS, derive, verify  # noqa: E402


class LegacyKdfVectorTests(unittest.TestCase):
    def test_six_hundred_thousand_round_vector(self):
        """用标准库核对旧密码算法及正确、错误口令的合成向量。"""
        password = "synthetic-test-password"
        salt = "00112233445566778899aabbccddeeff"
        self.assertEqual(ROUNDS, 600000)
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), ROUNDS
        ).hex()
        self.assertEqual(derive(password, salt), expected)
        self.assertTrue(verify(password, salt, expected))
        self.assertFalse(verify(password + "!", salt, expected))


if __name__ == "__main__":
    unittest.main()
