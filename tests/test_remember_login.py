import hashlib
import tempfile
import time
import unittest
from cloudflare_test_support import CloudCase
from app.market import Market, DomainError

class LocalRememberLogin(unittest.TestCase):
    def test_password_login_session_lasts_30_days_and_logout_revokes_it(self):
        with tempfile.TemporaryDirectory() as root:
            market=Market(root,trial=True)
            result=market.register_password('13900000991','remember-test','缓存测试')
            row=market.row('SELECT expires FROM sessions WHERE token=?',(hashlib.sha256(result['token'].encode()).hexdigest(),))
            self.assertAlmostEqual(row['expires']-time.time(),30*86400,delta=5)
            market.logout(result['token'])
            with self.assertRaises(DomainError): market.user(result['token'])

class CloudRememberLogin(CloudCase):
    async def test_cloud_login_uses_30_day_expiry(self):
        result=await self.req('/api/auth/register',uid=0,method='POST',body={
            'phone':'remember@test.invalid','nickname':'缓存测试',
            'salt':'12'*16,'digest':'ab'*32,'rounds':600000,
        })
        self.assertEqual(result.status,200)
        digest=hashlib.sha256(result.body['token'].encode()).hexdigest()
        expires=self.db.execute('SELECT expires FROM sessions WHERE token=?',(digest,)).fetchone()[0]
        self.assertAlmostEqual(expires-time.time(),30*86400,delta=5)
