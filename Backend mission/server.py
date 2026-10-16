import argparse,base64,ipaddress,json,mimetypes,os,time,threading,traceback
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,unquote
from app.market import Market,DomainError
from app.seed import seed as seed_data
from app.support.credit import CREDIT_RULES
from app.catalog.locations import BUILDINGS, BUILDING_GROUPS
from app.core.config import WEB,COLLEGES_JSON,data_dir
# Windows registry associations can label .js as text/plain. Core web types
# must be deterministic because browsers enforce nosniff for scripts/styles.
ASSET_TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml; charset=utf-8','.png':'image/png','.webp':'image/webp','.ico':'image/x-icon'}

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(20)
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
                expected=self.server.public_origin or 'http://'+self.headers.get('Host','')
                m.require(origin==expected,'不允许跨站请求',403)
            data={}
            if method=='POST':
                length=int(self.headers.get('Content-Length','0'));m.require(0<length<=8*1024*1024,'请求过大或为空',413)
                try:data=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeDecodeError):raise DomainError('无效JSON')
                m.require(isinstance(data,dict),'请求需为对象')
                client_ip=self.client_address[0]
                if self.server.trust_proxy:
                    # Single trusted ingress overwrites or appends the actual peer.
                    # Ignore user-supplied prefixes in an appended forwarded chain.
                    forwarded=self.headers.get('X-Forwarded-For','').split(',')[-1].strip()
                    try:client_ip=str(ipaddress.ip_address(forwarded))
                    except ValueError:pass
                self.server.limit(client_ip,p)
            if p=='/api/health' and method=='GET':
                m.row('SELECT 1');return self.respond({'ok':True,'trial':m.trial})
            if p=='/api/config':
                directory=COLLEGES_JSON
                colleges=json.loads(directory.read_text(encoding='utf-8'))['colleges'] if directory.exists() else []
                if m.trial:colleges=[{'source_name':'计算机工程学院'}]
                return self.respond({'simulation':True,'trial':m.trial,'auth_mode':'password' if m.trial else 'demo','phone_verified':False,'name':'转角','pilot':'计算机工程学院','campus':'广州校区','support_hours':'08:00–20:00','colleges':colleges,'buildings':BUILDINGS,'building_groups':BUILDING_GROUPS,'custom_location_allowed':True})
            if p=='/api/auth/code' and method=='POST':return self.respond(m.request_code(data.get('phone')))
            if p=='/api/auth/login' and method=='POST':return self.respond(m.login_password(data.get('phone'),data.get('password')) if m.trial else m.login(data.get('phone'),data.get('code')))
            if p=='/api/auth/register' and method=='POST':return self.respond(m.register_password(data.get('phone'),data.get('password'),data.get('nickname')))
            if p=='/api/auth/recover' and method=='POST':return self.respond(m.recover_password(data.get('phone'),data.get('recovery_code'),data.get('new_password')))
            if p=='/api/products/search' and method=='GET':return self.respond(m.search_products(self.optional_user(),query))
            if p=='/api/products' and method=='GET':return self.respond(m.products(self.optional_user(),query))
            if p=='/api/product' and method=='GET':return self.respond(m.product(int(query['id']),self.optional_user()))
            if p=='/api/profile' and method=='GET':
                u=int(query['id']);return self.respond({'user':m.profile(u),'products':m.products(self.optional_user(),{'seller':str(u)})})
            if p=='/api/posts' and method=='GET':return self.respond(m.posts(query.get('topic','')))
            if p=='/api/comments' and method=='GET':return self.respond(m.comments(int(query['id'])))
            if p.startswith('/media/'):
                fid=p.split('/')[-1];upload=m.row('SELECT * FROM uploads WHERE id=?',(fid,));m.require(upload,'图片不存在',404)
                if upload['private']:
                    uid=self.uid();m.require(uid==upload['user_id'] or m.can_view_evidence(uid,fid),'无权读取私密图片',403)
                else:
                    listed=any(fid in json.loads(r['data']).get('photos',[]).__str__() for r in m.rows("SELECT data FROM products WHERE status<>'removed'"))
                    uid=self.optional_user();m.require(listed or uid==upload['user_id'],'图片尚未发布',403)
                return self.respond(Path(upload['path']).read_bytes(),kind='image/webp')
            if not p.startswith('/api/'):
                web=self.server.web
                file=(web/(unquote(p).lstrip('/') if p!='/' else 'index.html')).resolve()
                root=str(web)
                try:inside=os.path.commonpath([root,str(file)])==root
                except ValueError:inside=False
                m.require(inside,'页面不存在',404)
                m.require(file.is_file(),'页面不存在',404)
                return self.respond(file.read_bytes(),kind=ASSET_TYPES.get(file.suffix.lower()) or mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            u=self.uid()
            if p=='/api/notifications' and method=='GET':return self.respond(m.notifications(u,int(query.get('before',0))))
            if p=='/api/notifications/read' and method=='POST':return self.respond(m.read_notifications(u,data))
            if p=='/api/drafts' and method=='GET':return self.respond(m.list_drafts(u))
            if p=='/api/draft':return self.respond(m.save_draft(u,data) if method=='POST' else m.get_draft(u,query.get('id','')))
            if p=='/api/draft/delete' and method=='POST':return self.respond(m.delete_draft(u,data.get('id')))
            if p=='/api/draft/publish' and method=='POST':return self.respond(m.publish_draft(u,data.get('id'),data.get('version')))
            if p=='/api/seller/products' and method=='GET':return self.respond(m.seller_products(u))
            if p=='/api/relist' and method=='POST':return self.respond(m.relist_draft(u,int(data['product_id'])))
            if p=='/api/admin/support':return self.respond(m.create_support(u,data) if method=='POST' else m.support_accounts(u))
            if p=='/api/admin/support/active' and method=='POST':return self.respond(m.set_support_active(u,int(data['user_id']),data.get('is_active')))
            if p=='/api/ticket/return' and method=='POST':return self.respond(m.return_action(u,int(data['id']),data['action']))
            if p=='/api/ticket/assign' and method=='POST':return self.respond(m.assign_ticket(u,int(data['id']),int(data['support_user_id']),data['reason']))
            if p=='/api/credit/rules' and method=='GET':return self.respond([{'key':key,**rule} for key,rule in CREDIT_RULES.items()])
            if p=='/api/credit/penalty' and method=='POST':return self.respond(m.apply_penalty(u,int(data['target_user_id']),int(data['ticket_id']),data['rule_key'],data['reason']))
            if p=='/api/credit/reverse' and method=='POST':return self.respond(m.reverse_penalty(u,int(data['audit_id']),int(data['ticket_id']),data['reason']))
            if p=='/api/credit/recover' and method=='POST':return self.respond(m.recover_credit(u,int(data['target_user_id']),int(data['ticket_id']),data['reason']))
            if p=='/api/auth/password' and method=='POST':return self.respond(m.change_password(u,data.get('old_password'),data.get('new_password')))
            if p=='/api/me':return self.respond(m.update_profile(u,data) if method=='POST' else m.profile(u))
            if p=='/api/auth/logout':m.logout(self.token());return self.respond({'ok':True})
            if p=='/api/product/edit':
                return self.respond(m.edit_product(u,int(data['id']),data['version'],data['fields']) if method=='POST' else m.product_edit(u,int(query['id'])))
            if p=='/api/publish' and method=='POST':return self.respond(m.publish(u,data))
            if p=='/api/my-products':return self.respond(m.my_products(u,query.get('status')))
            if p=='/api/product/status' and method=='POST':return self.respond(m.set_product_status(u,int(data['id']),data['action']))
            if p=='/api/upload' and method=='POST':
                try:content=base64.b64decode(data.get('content',''),validate=True)
                except ValueError:raise DomainError('无效图片编码')
                return self.respond(m.add_upload(u,content,data.get('angle'),bool(data.get('private',False))))
            if p=='/api/react' and method=='POST':return self.respond(m.react(u,int(data['product_id']),data['kind'],bool(data['on'])))
            if p=='/api/checkout' and method=='POST':return self.respond(m.checkout(u,data))
            if p=='/api/orders':return self.respond(m.orders(u))
            if p=='/api/order':return self.respond(m.order(u,int(query['id'])))
            if p=='/api/order/action' and method=='POST':return self.respond(m.order_action(u,int(data['id']),data['action'],data))
            if p=='/api/order/update' and method=='POST':return self.respond(m.update_order(u,int(data['id']),data))
            if p=='/api/order/change' and method=='POST':return self.respond(m.respond_change(u,int(data['id']),bool(data['accept'])))
            if p=='/api/offers':return self.respond(m.offers(u))
            if p=='/api/offer' and method=='POST':return self.respond(m.offer(u,int(data['product_id']),data['amount']))
            if p=='/api/offer/accept' and method=='POST':return self.respond(m.accept_offer(u,int(data['id']),bool(data['accept'])))
            if p=='/api/tickets':return self.respond(m.create_ticket(u,data) if method=='POST' else m.tickets(u))
            if p=='/api/ticket':return self.respond(m.ticket(u,int(query['id'])))
            if p=='/api/ticket/reply' and method=='POST':return self.respond(m.reply_ticket(u,int(data['id']),data))
            if p=='/api/ticket/resolve' and method=='POST':
                if 'amount_yuan' in data:data['amount']=m._yuan_to_cents(data['amount_yuan'])
                return self.respond(m.resolve_ticket(u,int(data['id']),data))
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
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(32)
        super().__init__(*args,**kwargs)
    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()
    def limit(self,ip,path):
        now=time.time();key=(ip,path)
        with self.rate_lock:
            hist=[t for t in self.rates.get(key,[]) if now-t<60]
            cap=20 if path.startswith('/api/auth') else 120
            if len(hist)>=cap:raise DomainError('操作过于频繁，请稍后再试',429)
            hist.append(now);self.rates[key]=hist

def make_server(root,port=8080,seed=False,trial=False,host='127.0.0.1',public_origin=None,trust_proxy=False,admin=None,web=None):
    if trial and seed:raise ValueError('学院试用不能载入共享演示账号或商品')
    if host not in ['127.0.0.1','localhost'] and not trial:raise ValueError('本地演示版只能绑定本机地址')
    if public_origin:
        public_origin=public_origin.rstrip('/');parsed=urlsplit(public_origin)
        if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('公网地址必须是完整HTTPS源地址，不含路径或账号密码')
    if host not in ['127.0.0.1','localhost'] and not public_origin:raise ValueError('公网绑定前需配置HUALI_PUBLIC_ORIGIN并通过HTTPS代理访问')
    market=Market(root,trial=trial)
    if admin:market.bootstrap_admin(*admin)
    server=Server((host,port),Handler);server.market=market;server.public_origin=public_origin;server.trust_proxy=trust_proxy;server.rates={};server.rate_lock=threading.Lock()
    server.web=Path(web).resolve() if web else WEB
    if seed:seed_data(server.market)
    return server

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')));ap.add_argument('--data',default=os.environ.get('HUALI_DATA_DIR'));ap.add_argument('--no-seed',action='store_true');ap.add_argument('--trial',action='store_true');ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--public-origin',default=os.environ.get('HUALI_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL'));ap.add_argument('--trust-proxy',action='store_true');ap.add_argument('--web',default=os.environ.get('HUALI_WEB_DIR'));args=ap.parse_args()
    root=args.data or data_dir(args.trial)
    phone=os.environ.get('HUALI_ADMIN_PHONE');password=os.environ.get('HUALI_ADMIN_PASSWORD')
    if bool(phone)!=bool(password):ap.error('管理员手机号与密码必须同时配置，或均不配置')
    if phone and not args.trial:ap.error('管理员初始化仅供--trial模式使用')
    try:server=make_server(root,args.port,not args.trial and not args.no_seed,trial=args.trial,host=args.host,public_origin=args.public_origin,trust_proxy=args.trust_proxy,admin=(phone,password) if phone else None,web=args.web)
    except (DomainError,ValueError) as error:ap.error(str(error))
    def timer():
        while True:
            try:
                server.market.tick()
                server.market.cleanup_drafts()
                backups=list((server.market.root/'backups').glob('*.zip')) if (server.market.root/'backups').exists() else []
                if not backups or time.time()-max(x.stat().st_mtime for x in backups)>86400:server.market._backup()
            except Exception:traceback.print_exc()
            time.sleep(30)
    threading.Thread(target=timer,daemon=True).start()
    mode='计算机学院试用版 · 手机号密码登录 · 模拟交易' if args.trial else '本地模拟版'
    print(f'转角 · {mode} · port {server.server_port} · Ctrl+C停止',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
