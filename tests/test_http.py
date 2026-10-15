import unittest, tempfile, threading, json, urllib.request, urllib.error, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import Handler, make_server

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
    def test_core_asset_types_ignore_incorrect_windows_registry_mappings(self):
        with patch('server.mimetypes.guess_type',return_value=('text/plain',None)):
            for path,expected in [('/','text/html'),('/app.js','text/javascript'),('/market.css','text/css')]:
                with self.subTest(path=path):
                    status,body,headers=self.req(path)
                    self.assertEqual(status,200)
                    self.assertTrue(headers['Content-Type'].startswith(expected),headers['Content-Type'])
                    self.assertIn('charset=utf-8',headers['Content-Type'])
                    self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
                    self.assertTrue(body)
    def test_static_files_without_python39_path_method(self):
        with patch.object(Path,'is_relative_to',side_effect=AttributeError('unavailable before Python 3.9'),create=True):
            self.assertEqual(self.req('/')[0],200)
            self.assertEqual(self.req('/market.css')[0],200)
            self.assertEqual(self.req('/..%2fserver.py')[0],404)
    def test_static_root_rejects_sibling_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);web=root/'web';web.mkdir()
            outside=root/'web-private';outside.mkdir();(outside/'secret.txt').write_text('private')
            (web/'index.html').write_text('home')
            (web/'escape').symlink_to(outside,target_is_directory=True)
            with patch('server.WEB',web):
                self.assertEqual(self.req('/')[0],200)
                self.assertEqual(self.req('/..%2fweb-private/secret.txt')[0],404)
                self.assertEqual(self.req('/escape/secret.txt')[0],404)
    def test_bearer_token_without_python39_string_method(self):
        class LegacyString(str):
            def removeprefix(self,*args):raise AttributeError('unavailable before Python 3.9')
        for header,expected in [('Bearer session-token','session-token'),('Basic other',''),('','')]:
            self.assertEqual(Handler.token(SimpleNamespace(headers={'Authorization':LegacyString(header)})),expected)
    def test_college_directory_with_non_utf8_system_default(self):
        read_text=Path.read_text
        def legacy_read_text(path,*args,**kwargs):
            if 'encoding' not in kwargs:kwargs['encoding']='ascii'
            return read_text(path,*args,**kwargs)
        with patch.object(Path,'read_text',legacy_read_text):
            status,body,_=self.req('/api/config')
        self.assertEqual(status,200)
        self.assertTrue(json.loads(body)['colleges'])
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
