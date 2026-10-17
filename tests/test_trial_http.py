import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from server import make_server


class TrialHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=make_server(self.tmp.name,0,trial=True,public_origin='https://campus.example')
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def req(self,path,data=None,token=None,origin='https://campus.example',extra_headers=None):
        headers={'Content-Type':'application/json','Origin':origin}
        if extra_headers:headers.update(extra_headers)
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:return error.code,json.loads(error.read())
    def register(self,phone='13900000011'):
        status,result=self.req('/api/auth/register',{'phone':phone,'password':'TrialPassword2026!','nickname':'试用同学','role':'admin'})
        self.assertEqual(status,200,result)
        return result

    def test_trial_config_and_shared_login_closed(self):
        status,config=self.req('/api/config')
        self.assertEqual(status,200)
        self.assertEqual(config['auth_mode'],'password')
        self.assertTrue(config['trial'])
        self.assertEqual(self.req('/api/auth/code',{'phone':'13800000003'})[0],403)
        self.assertEqual(self.req('/api/auth/login',{'phone':'13800000003','code':'123456'})[0],401)

    def test_local_host_origin_allowed_while_public_origin_is_configured(self):
        # 回归：--lan 会把 public_origin 固定成局域网地址（如 http://192.168.0.19:8081），
        # 但用户常从 http://127.0.0.1:8081 打开。浏览器对 ES 模块请求一定带 Origin，
        # 若只认 public_origin，/src/main.js 会 403，页面永远停在加载文案。
        # 本机名/localhost/局域网 IP 指向同一实例，都应放行。
        status,config=self.req('/api/config',origin=self.base)
        self.assertEqual(status,200,config)
        self.assertTrue(config['trial'])
        # 真正的跨站 Origin 仍必须拒绝（CSRF 防护不受影响）。
        self.assertEqual(self.req('/api/auth/register',{'phone':'13900000022','password':'TrialPassword2026!','nickname':'跨站'},origin='https://evil.example')[0],403)

    def test_https_proxy_origin_registration_and_role_boundary(self):
        result=self.register()
        token=result['token']
        self.assertEqual(result['user']['role'],'user')
        self.assertEqual(self.req('/api/me',token=token)[0],200)
        for path in ['/api/admin','/api/reconcile']:
            self.assertEqual(self.req(path,token=token)[0],403)
        self.assertEqual(self.req('/api/backup',{},token)[0],403)
        self.assertEqual(self.req('/api/auth/login',{'phone':'13900000011','password':'TrialPassword2026!'})[0],200)
        self.assertEqual(self.req('/api/auth/login',{'phone':'13900000011','password':'TrialPassword2026!'},origin='https://evil.example')[0],403)

    def test_password_change_logout_and_health(self):
        result=self.register();token=result['token']
        self.assertEqual(self.req('/api/auth/password',{'old_password':'TrialPassword2026!','new_password':'DifferentPassword2026!'},token)[0],200)
        self.assertEqual(self.req('/api/me',token=token)[0],401)
        status,result=self.req('/api/auth/login',{'phone':'13900000011','password':'DifferentPassword2026!'})
        self.assertEqual(status,200)
        self.assertEqual(self.req('/api/auth/logout',{},result['token'])[0],200)
        self.assertEqual(self.req('/api/me',token=result['token'])[0],401)
        self.assertEqual(self.req('/api/health')[1]['ok'],True)

    def test_invalid_request_and_auth_rate_limit(self):
        self.assertEqual(self.req('/api/auth/register',{'phone':'bad','password':'short','nickname':'x'})[0],400)
        statuses=[self.req('/api/auth/register',{'phone':'bad','password':'short','nickname':'x'})[0] for _ in range(20)]
        self.assertEqual(statuses[-1],429)

    def test_oversized_declared_body_rejected_before_reading(self):
        status,_=self.req('/api/auth/register',{},extra_headers={'Content-Length':str(8*1024*1024+1)})
        self.assertEqual(status,413)

    def test_trial_never_seeds_shared_demo_accounts(self):
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):make_server(tmp,0,seed=True,trial=True)

    def test_trusted_proxy_does_not_accept_forged_forwarded_prefix_for_rate_limit(self):
        self.server.trust_proxy=True
        statuses=[]
        for index in range(21):
            # A single trusted ingress appends the actual client after untrusted input.
            statuses.append(self.req('/api/auth/register',{'phone':'bad','password':'short','nickname':'x'},extra_headers={'X-Forwarded-For':f'192.0.2.{index+1}, 203.0.113.10'})[0])
        self.assertEqual(statuses[-1],429)


if __name__=='__main__':unittest.main()
