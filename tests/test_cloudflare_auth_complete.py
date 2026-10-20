"""Complete cloud credential lifecycle against isolated SQLite/D1."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
from cloudflare_test_support import CloudCase, ROOT
from app.cloudflare.api import Api as BaseApi
from app.cloudflare.auth_api import AuthApi, AUTH_ROUTES
from app.cloudflare.http import guard, path_of
from app.cloudflare.crypto import session_digest

if issubclass(BaseApi, AuthApi):
    DomainApi=BaseApi
else:
    class DomainApi(AuthApi,BaseApi):
        async def dispatch(self,r):
            route=AUTH_ROUTES.get(path_of(r))
            if route:return await getattr(self,route[1])(r)
            return await super().dispatch(r)

class AuthCompleteTests(CloudCase):
    def setUp(self):
        super().setUp()
        self.api=DomainApi(self.api.env)
        for uid in range(1,6):
            self.db.execute('INSERT INTO password_credentials VALUES(?,?,?,?,?)',(uid,'12'*16,'ab'*32,10000,hashlib.sha256(f'recovery-{uid}'.encode()).hexdigest()))
        self.body={'salt':'34'*16,'digest':'cd'*32,'rounds':600000}
    async def post(self,path,body=None,uid=2):return await self.req(path,uid=uid,method='POST',body=body or {})
    async def test_authenticated_salt_uses_existing_legacy_parameters(self):
        result=await self.req('/api/auth/salt');self.assertEqual(result.status,200);self.assertEqual(result.body,{'salt':'12'*16,'rounds':10000})
        self.assertEqual((await self.req('/api/auth/salt',uid=0)).status,401)
        result=await self.req('/api/auth/salt?phone=u3%40test.invalid',uid=0)
        self.assertEqual(result.body,{'salt':'12'*16,'rounds':10000})
        result=await self.req('/api/auth/salt?phone=unknown%40test.invalid',uid=0)
        self.assertEqual(result.body,{'salt':'00'*16,'rounds':600000})
    async def test_password_rotates_recovery_and_revokes_all_sessions(self):
        self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(session_digest('second'),2,9999999999))
        result=await self.post('/api/auth/password',{**self.body,'old_digest':'ab'*32})
        self.assertEqual(result.status,200);self.assertTrue(result.body['recovery_code'])
        row=dict(self.db.execute('SELECT * FROM password_credentials WHERE user_id=2').fetchone())
        self.assertEqual(row['digest'],self.body['digest']);self.assertEqual(row['rounds'],600000)
        self.assertEqual(row['recovery_digest'],hashlib.sha256(result.body['recovery_code'].encode()).hexdigest())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=2').fetchone()[0],0)
    async def test_wrong_old_digest_and_low_rounds_do_not_mutate(self):
        self.assertEqual((await self.post('/api/auth/password',{**self.body,'old_digest':'ef'*32})).status,401)
        self.assertEqual((await self.post('/api/auth/password',{**self.body,'rounds':10000,'old_digest':'ab'*32})).status,400)
        self.assertEqual(self.db.execute('SELECT digest FROM password_credentials WHERE user_id=2').fetchone()[0],'ab'*32)
    async def test_recover_is_single_use_and_blocked_for_inactive_account(self):
        d={**self.body,'phone':'u2@test.invalid','recovery_code':'recovery-2'}
        result=await self.post('/api/auth/recover',d,uid=0);self.assertEqual(result.status,200)
        self.assertEqual((await self.post('/api/auth/recover',d,uid=0)).status,401)
        self.db.execute("UPDATE users SET status='deactivated' WHERE id=3")
        self.assertEqual((await self.post('/api/auth/recover',{**self.body,'phone':'u3@test.invalid','recovery_code':'recovery-3'},uid=0)).status,403)
    async def test_password_race_cannot_overwrite_new_credentials(self):
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.db.execute("UPDATE password_credentials SET digest=? WHERE user_id=2",('ef'*32,))
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        result=await self.post('/api/auth/password',{**self.body,'old_digest':'ab'*32});self.assertEqual(result.status,409)
        self.assertEqual(self.db.execute('SELECT digest FROM password_credentials WHERE user_id=2').fetchone()[0],'ef'*32)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=2').fetchone()[0],1)
    async def test_recovery_race_and_status_race_roll_back(self):
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.db.execute("UPDATE users SET status='disabled' WHERE id=2")
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        result=await self.post('/api/auth/recover',{**self.body,'phone':'u2@test.invalid','recovery_code':'recovery-2'},uid=0)
        self.assertEqual(result.status,409)
        self.assertEqual(self.db.execute('SELECT digest FROM password_credentials WHERE user_id=2').fetchone()[0],'ab'*32)
    async def test_deactivate_retains_records_delists_and_revokes(self):
        self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,status) VALUES(10,2,3,'completed')")
        self.db.execute("INSERT INTO tickets(id,user_id,order_id,status) VALUES(10,2,10,'resolved')")
        self.db.execute("INSERT INTO products(id,seller_id,title,status,data) VALUES(10,2,'测试','available','{}')")
        result=await self.post('/api/auth/deactivate');self.assertEqual(result.status,200)
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=2').fetchone()[0],'deactivated')
        self.assertEqual(self.db.execute('SELECT status FROM products WHERE id=10').fetchone()[0],'removed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM password_credentials WHERE user_id=2').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=2').fetchone()[0],0)
    async def test_open_orders_and_other_party_ticket_prevent_deactivate(self):
        self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,status) VALUES(10,2,3,'paid')")
        self.assertEqual((await self.post('/api/auth/deactivate')).status,400)
        self.db.execute("UPDATE orders SET status='completed' WHERE id=10")
        self.db.execute("INSERT INTO tickets(id,user_id,order_id,status) VALUES(10,3,10,'open')")
        self.assertEqual((await self.post('/api/auth/deactivate')).status,400)
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=2').fetchone()[0],'active')
    async def test_last_administrator_and_order_race_guard(self):
        self.assertEqual((await self.post('/api/auth/deactivate',uid=1)).status,400)
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.db.execute("INSERT INTO orders(id,buyer_id,seller_id,status) VALUES(10,2,3,'paid')")
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        self.assertEqual((await self.post('/api/auth/deactivate')).status,409)
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=2').fetchone()[0],'active')
    async def test_recovery_secret_changed_after_read_cannot_be_reused(self):
        original=self.api.db.guarded_batch
        updated=hashlib.sha256(b'another-recovery').hexdigest()
        async def race(sql,params,statements,**kw):
            self.db.execute('UPDATE password_credentials SET recovery_digest=? WHERE user_id=2',(updated,))
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        result=await self.post('/api/auth/recover',{**self.body,'phone':'u2@test.invalid','recovery_code':'recovery-2'},uid=0)
        self.assertEqual(result.status,409)
        row=self.db.execute('SELECT digest,recovery_digest FROM password_credentials WHERE user_id=2').fetchone()
        self.assertEqual(tuple(row),('ab'*32,updated))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=2').fetchone()[0],1)

    async def test_password_revoked_session_race_cannot_rotate(self):
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.db.execute('DELETE FROM sessions WHERE user_id=2')
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        result=await self.post('/api/auth/password',{**self.body,'old_digest':'ab'*32})
        self.assertEqual(result.status,409)
        self.assertEqual(self.db.execute('SELECT digest FROM password_credentials WHERE user_id=2').fetchone()[0],'ab'*32)

    async def test_last_admin_guard_rechecks_other_admin_status(self):
        self.db.execute("UPDATE users SET role='admin' WHERE id=3")
        original=self.api.db.guarded_batch
        async def race(sql,params,statements,**kw):
            self.db.execute("UPDATE users SET status='deactivated' WHERE id=3")
            return await original(sql,params,statements,**kw)
        self.api.db.guarded_batch=race
        result=await self.post('/api/auth/deactivate',uid=1)
        self.assertEqual(result.status,409)
        self.assertEqual(self.db.execute('SELECT status FROM users WHERE id=1').fetchone()[0],'active')

    def test_frontend_password_uses_saved_salt_and_new_600k_credential(self):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        source=(ROOT/'web 7M/src/actions/account.js').read_text(encoding='utf-8')
        source=re.sub(r'^import .*?;\s*','',source,flags=re.M)
        source=source.replace('export const ','const ')
        script="""import crypto from 'node:crypto';import assert from 'node:assert/strict';
        const calls=[];let sent;
        Object.assign(globalThis,{$:()=>null,toast(){},state:{config:{auth_mode:'client_kdf',pbkdf2_rounds:10000}},
        api:async(path,body)=>{calls.push(path);if(path==='/auth/salt')return {salt:'12121212121212121212121212121212',rounds:10000};sent=body;return {recovery_code:'new'};},
        randomSaltHex:()=> '34343434343434343434343434343434',pbkdf2Hex:async(p,s,r)=>crypto.pbkdf2Sync(p,Buffer.from(s,'hex'),r,32,'sha256').toString('hex'),
        clearAccount(){},go(){},render:async()=>{},recoveryNotice(){},loginModal(){},trialLoginModal(){},changePasswordModal(){},setLogin(){},assert,nodeCrypto:crypto,calls,getSent:()=>sent});
        """
        source+="""\nawait submits['change-password-form']({form:{},d:{old_password:'old-password',new_password:'new-password',password_confirm:'new-password'}});
        assert.ok(calls.includes('/auth/salt'));const body=getSent();
        assert.equal(body.old_digest,nodeCrypto.pbkdf2Sync('old-password',Buffer.from('12'.repeat(16),'hex'),10000,32,'sha256').toString('hex'));
        assert.equal(body.rounds,600000);assert.equal(body.salt,'34'.repeat(16));
        assert.equal(body.digest,nodeCrypto.pbkdf2Sync('new-password',Buffer.from('34'.repeat(16),'hex'),600000,32,'sha256').toString('hex'));
        assert.equal(body.new_password,undefined);assert.equal(body.old_password,undefined);
        """
        script+='await import("data:text/javascript;base64,"+Buffer.from('+json.dumps(source)+').toString("base64"));'
        result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)

