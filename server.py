import argparse,base64,json,mimetypes,os,time,threading,traceback
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,unquote
from market import Market,DomainError
from seed import seed as seed_data
WEB=Path(__file__).parent/'web'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,data,status=200,kind='application/json; charset=utf-8'):
        body=json.dumps(data,ensure_ascii=False).encode() if kind.startswith('application/json') else data
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(body)
    def token(self):
        authorization=self.headers.get('Authorization','')
        return authorization[len('Bearer '):] if authorization.startswith('Bearer ') else ''
    def uid(self):return self.server.market.user(self.token())
    def optional_user(self):
        try:return self.uid()
        except DomainError:return None
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def handle_request(self,method):
        m=self.server.market;p=urlsplit(self.path).path;query={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
        try:
            origin=self.headers.get('Origin')
            if origin:
                expected='http://'+self.headers.get('Host','')
                m.require(origin==expected,'不允许跨站请求',403)
            data={}
            if method=='POST':
                length=int(self.headers.get('Content-Length','0'));m.require(0<length<=8*1024*1024,'请求过大或为空',413)
                try:data=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeDecodeError):raise DomainError('无效JSON')
                m.require(isinstance(data,dict),'请求需为对象')
                self.server.limit(self.client_address[0],p)
            if p=='/api/config':
                directory=Path(__file__).parent/'docs/research/guangzhou-college-options.json'
                colleges=json.loads(directory.read_text(encoding='utf-8'))['colleges'] if directory.exists() else []
                return self.respond({'simulation':True,'name':'华立转角','pilot':'计算机工程学院','campus':'广州校区','support_hours':'08:00–20:00','colleges':colleges,'buildings':['本科综合楼','行政楼','L17','L18','G1主楼','G1副楼','G2','G3','G4主楼','G4副楼','A1','A2','A3','A4','L16','L13','L12','L11','L10','L9','L8','L7','L4','L3','L2','L1','L5','L6','L15','7号楼仓库','D2','D6','D5']})
            if p=='/api/auth/code' and method=='POST':return self.respond(m.request_code(data.get('phone')))
            if p=='/api/auth/login' and method=='POST':return self.respond(m.login(data.get('phone'),data.get('code')))
            if p=='/api/products' and method=='GET':return self.respond(m.products(self.optional_user(),query))
            if p=='/api/product' and method=='GET':return self.respond(m.product(int(query['id']),self.optional_user()))
            if p=='/api/profile' and method=='GET':
                u=int(query['id']);return self.respond({'user':m.profile(u),'products':m.products(self.optional_user(),{'seller':str(u)})})
            if p=='/api/posts' and method=='GET':return self.respond(m.posts(query.get('topic','')))
            if p=='/api/comments' and method=='GET':return self.respond(m.comments(int(query['id'])))
            if p.startswith('/media/'):
                fid=p.split('/')[-1];upload=m.row('SELECT * FROM uploads WHERE id=?',(fid,));m.require(upload,'图片不存在',404)
                if upload['private']:
                    uid=self.uid();m.require(uid==upload['user_id'] or m.profile(uid)['role'] in ['admin','support'],'无权读取私密图片',403)
                else:
                    listed=any(fid in json.loads(r['data']).get('photos',[]).__str__() for r in m.rows("SELECT data FROM products WHERE status<>'removed'"))
                    uid=self.optional_user();m.require(listed or uid==upload['user_id'],'图片尚未发布',403)
                return self.respond(Path(upload['path']).read_bytes(),kind='image/webp')
            if not p.startswith('/api/'):
                file=(WEB/(unquote(p).lstrip('/') if p!='/' else 'index.html')).resolve()
                root=str(WEB.resolve())
                try:inside=os.path.commonpath([root,str(file)])==root
                except ValueError:inside=False
                m.require(inside,'页面不存在',404)
                m.require(file.is_file(),'页面不存在',404)
                return self.respond(file.read_bytes(),kind=mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            u=self.uid()
            if p=='/api/me':return self.respond(m.update_profile(u,data) if method=='POST' else m.profile(u))
            if p=='/api/auth/logout':m.logout(self.token());return self.respond({'ok':True})
            if p=='/api/publish' and method=='POST':return self.respond(m.publish(u,data))
            if p=='/api/upload' and method=='POST':
                try:content=base64.b64decode(data.get('content',''),validate=True)
                except ValueError:raise DomainError('无效图片编码')
                return self.respond(m.add_upload(u,content,data.get('angle'),bool(data.get('private',False))))
            if p=='/api/react' and method=='POST':return self.respond(m.react(u,int(data['product_id']),data['kind'],bool(data['on'])))
            if p=='/api/checkout' and method=='POST':return self.respond(m.checkout(u,data))
            if p=='/api/orders':return self.respond(m.orders(u))
            if p=='/api/order':return self.respond(m.order(u,int(query['id'])))
            if p=='/api/order/action' and method=='POST':return self.respond(m.order_action(u,int(data['id']),data['action'],data))
            if p=='/api/order/change' and method=='POST':return self.respond(m.respond_change(u,int(data['id']),bool(data['accept'])))
            if p=='/api/offers':return self.respond(m.offers(u))
            if p=='/api/offer' and method=='POST':return self.respond(m.offer(u,int(data['product_id']),data['amount']))
            if p=='/api/offer/accept' and method=='POST':return self.respond(m.accept_offer(u,int(data['id']),bool(data['accept'])))
            if p=='/api/tickets':return self.respond(m.create_ticket(u,data) if method=='POST' else m.tickets(u))
            if p=='/api/ticket':return self.respond(m.ticket(u,int(query['id'])))
            if p=='/api/ticket/reply' and method=='POST':return self.respond(m.reply_ticket(u,int(data['id']),data))
            if p=='/api/ticket/resolve' and method=='POST':return self.respond(m.resolve_ticket(u,int(data['id']),data))
            if p=='/api/credit' and method=='POST':return self.respond(m.credit_action(u,int(data['target']),data['delta'],data['reason'],int(data['ticket_id'])))
            if p=='/api/credit/history':return self.respond(m.credit_history(u))
            if p=='/api/review' and method=='POST':return self.respond(m.review(u,int(data['order_id']),data['rating'],data['body']))
            if p=='/api/rooms':return self.respond(m.rooms(u))
            if p=='/api/rooms/join' and method=='POST':return self.respond(m.join_room(u,data['kind']))
            if p=='/api/rooms/private' and method=='POST':return self.respond(m.private_room(u,int(data['peer'])))
            if p=='/api/messages':return self.respond(m.send_message(u,int(data['room_id']),data['body'],data['key']) if method=='POST' else m.messages(u,int(query['room_id']),int(query.get('after',0))))
            if p=='/api/block' and method=='POST':return self.respond(m.block(u,int(data['target']),bool(data.get('enabled',True))))
            if p=='/api/posts' and method=='POST':return self.respond(m.add_post(u,data))
            if p=='/api/comments' and method=='POST':return self.respond(m.comment(u,int(data['post_id']),data['body']))
            if p=='/api/moderate' and method=='POST':return self.respond(m.moderate(u,data))
            if p=='/api/nominate' and method=='POST':return self.respond(m.nominate(u,data))
            if p=='/api/admin':
                m.staff(u);return self.respond({'users':m.rows('SELECT id,nickname,college,score,role FROM users'),'audit':m.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 100'),'nominations':m.rows('SELECT n.*,u.nickname,r.name FROM nominations n JOIN users u ON u.id=n.user_id JOIN rooms r ON r.id=n.room_id')})
            if p=='/api/admin/nominate' and method=='POST':
                m.require(m.profile(u)['role']=='admin','仅平台管理员可任命',403)
                with m.tx() as c:
                    n=c.execute("SELECT * FROM nominations WHERE id=? AND status='pending'",(int(data['id']),)).fetchone();m.require(n,'申请不存在或已处理')
                    c.execute("UPDATE nominations SET status='approved' WHERE id=?",(n['id'],));c.execute("UPDATE members SET role='moderator' WHERE room_id=? AND user_id=?",(n['room_id'],n['user_id']))
                    c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,n['user_id'],'appointment','群管理员申请审核通过',time.time()))
                return self.respond({'ok':True})
            if p=='/api/reconcile':return self.respond(m.reconcile(u))
            if p=='/api/backup' and method=='POST':return self.respond({'ok':True,'file':Path(m.backup(u)).name})
            raise DomainError('接口不存在',404)
        except DomainError as e:self.respond({'error':str(e)},e.status)
        except (ValueError,TypeError,KeyError) as e:self.respond({'error':'输入格式或字段不完整'},400)
        except Exception:
            traceback.print_exc();self.respond({'error':'服务暂时异常，请重试'},500)

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def limit(self,ip,path):
        now=time.time();key=(ip,path)
        with self.rate_lock:
            hist=[t for t in self.rates.get(key,[]) if now-t<60]
            cap=20 if path.startswith('/api/auth') else 120
            if len(hist)>=cap:raise DomainError('操作过于频繁，请稍后再试',429)
            hist.append(now);self.rates[key]=hist

def make_server(root,port=8080,seed=False):
    server=Server(('127.0.0.1',port),Handler);server.market=Market(root);server.rates={};server.rate_lock=threading.Lock()
    if seed:seed_data(server.market)
    return server

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8080);ap.add_argument('--data',default=str(Path(__file__).parent/'var'));ap.add_argument('--no-seed',action='store_true');args=ap.parse_args()
    server=make_server(args.data,args.port,not args.no_seed)
    def timer():
        while True:
            try:
                server.market.tick()
                backups=list((server.market.root/'backups').glob('*.zip')) if (server.market.root/'backups').exists() else []
                if not backups or time.time()-max(x.stat().st_mtime for x in backups)>86400:server.market.backup(3)
            except Exception:traceback.print_exc()
            time.sleep(30)
    threading.Thread(target=timer,daemon=True).start()
    print(f'华立转角 · 本地模拟版 · port {server.server_port} · Ctrl+C停止',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
