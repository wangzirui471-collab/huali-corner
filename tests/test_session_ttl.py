"""会话有效期与滑动续期（2026-10 用户要求「电脑上登录过就不用再登录」）。

规则：
  · 登录签发 30 天有效期的会话；
  · 每次带 token 访问时，剩余不足 7 天自动续满 30 天（常用设备不掉线）；
  · 闲置超过 30 天会话失效，必须重新登录（不是永久 token）。
"""
import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from app.market import Market, DomainError
from app.account.service import SESSION_TTL, SESSION_RENEW


class SessionTtlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.market = Market(self.tmp.name, trial=True)
        self.password = 'StudyAtHuali-2026!'

    def register(self, phone='13900000011'):
        return self.market.register_password(phone, self.password, '会话同学')

    def session_row(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        return self.market.row('SELECT * FROM sessions WHERE token=?', (digest,))

    def test_login_issues_30_day_session(self):
        token = self.register()['token']
        row = self.session_row(token)
        remaining = row['expires'] - time.time()
        self.assertAlmostEqual(remaining, SESSION_TTL, delta=120)

    def test_short_session_is_renewed_on_use(self):
        token = self.register()['token']
        digest = hashlib.sha256(token.encode()).hexdigest()
        soon = time.time() + 3 * 86400          # 只剩 3 天
        with self.market.tx() as c:
            c.execute('UPDATE sessions SET expires=? WHERE token=?', (soon, digest))
        self.market.user(token)                 # 访问一次
        renewed = self.session_row(token)['expires'] - time.time()
        self.assertAlmostEqual(renewed, SESSION_TTL, delta=120)

    def test_fresh_session_is_not_rewritten(self):
        """剩余充足时不写库——避免每次请求都 UPDATE。"""
        token = self.register()['token']
        digest = hashlib.sha256(token.encode()).hexdigest()
        before = self.session_row(token)['expires']
        self.market.user(token)
        self.assertEqual(self.session_row(token)['expires'], before)

    def test_expired_session_requires_login(self):
        token = self.register()['token']
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.market.tx() as c:
            c.execute('UPDATE sessions SET expires=? WHERE token=?', (time.time() - 1, digest))
        with self.assertRaises(DomainError) as ctx:
            self.market.user(token)
        self.assertEqual(ctx.exception.status, 401)

    def test_logout_revokes_session(self):
        token = self.register()['token']
        self.market.logout(token)
        with self.assertRaises(DomainError):
            self.market.user(token)

    def test_renew_threshold_leaves_a_week(self):
        """续期阈值必须小于有效期，且留出至少 7 天的安全余量。"""
        self.assertLess(SESSION_RENEW, SESSION_TTL)
        self.assertGreaterEqual(SESSION_TTL - SESSION_RENEW, 7 * 86400)


if __name__ == '__main__':
    unittest.main()
