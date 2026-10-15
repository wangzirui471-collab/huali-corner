import unittest, tempfile, threading, json, urllib.request, urllib.error, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import make_server

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=make_server(self.tmp.name,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def req(self,path,data=None,token=None):
        h={'Content-Type':'application/json'}
        if token:h['Authorization']='Bearer '+token
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=h)) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def test_public_home_api_and_no_cache(self):
        status,body,h=self.req('/');self.assertEqual(status,200);self.assertIn('华立转角',body.decode())
        status,body,h=self.req('/api/products');self.assertEqual(status,200);self.assertIsInstance(json.loads(body),list)
        self.assertEqual(h['Cache-Control'],'no-store')
    def test_auth_required_and_origin_guard(self):
        self.assertEqual(self.req('/api/orders')[0],401)
        req=urllib.request.Request(self.base+'/api/auth/code',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)
    def test_demo_login_and_private_route(self):
        status,b,h=self.req('/api/auth/code',{'phone':'13800000011'});code=json.loads(b)['demo_code']
        status,b,h=self.req('/api/auth/login',{'phone':'13800000011','code':code});token=json.loads(b)['token']
        self.assertEqual(self.req('/api/me',token=token)[0],200)
        self.assertEqual(self.req('/api/admin',token=token)[0],403)
        self.assertNotEqual(self.req('/../../market.py')[0],200)

if __name__=='__main__':unittest.main()
