import argparse,base64,ipaddress,json,mimetypes,os,secrets,socket,time,threading,traceback
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs,unquote
from app.market import Market,DomainError
from app.seed import seed as seed_data
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
                # 允许的 Origin 有两个来源，缺一不可：
                #   1. 显式配置的 public_origin（反代/公网域名）；
                #   2. 请求自身的 Host（X-Forwarded-Proto 推导，直连则 http）。
                # 只留 (1) 会在 --lan 时把本机访问憋死：--lan 把 public_origin 固定成
                # http://<局域网IP>:8081，而浏览器打开 http://127.0.0.1:8081 时，Chrome 对
                # ES 模块请求一定带 Origin，于是 /src/main.js 被 403、页面永远停在加载文案。
                # 本机名、localhost、局域网 IP 指向的是同一个实例，都该放行；
                # 而跨站页面（evil.example）的 Origin 既不是 public_origin 也不是本站 Host，
                # 仍然被拦住，CSRF 防护不受影响。
                proto=(self.headers.get('X-Forwarded-Proto') or 'http').split(',')[0].strip().lower()
                host=self.headers.get('Host','')
                allowed={f'{proto}://'+host,'http://'+host,'https://'+host}
                if self.server.public_origin:allowed.add(self.server.public_origin)
                m.require(origin in allowed,'不允许跨站请求',403)
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
                return self.respond({'simulation':True,'trial':m.trial,'auth_mode':'password' if m.trial else 'demo','phone_verified':False,'name':'华立转角','pilot':'计算机工程学院','campus':'广州校区','support_hours':'08:00–20:00','colleges':colleges,'buildings':['本科综合楼','行政楼','7号楼仓库','A1','A2','A3','A4','B1','B2','B3','B4','B9','C1','C2','C3','C4','C5','C6','C7','C8','D1','D2','D5','D6','G1主楼','G1副楼','G2','G3','G4主楼','G4副楼','L1','L2','L3','L4','L5','L6','L7','L8','L9','L10','L11','L12','L13','L15','L16','L17','L18']})
            if p=='/api/auth/code' and method=='POST':return self.respond(m.request_code(data.get('phone')))
            if p=='/api/auth/login' and method=='POST':return self.respond(m.login_password(data.get('phone'),data.get('password')) if m.trial else m.login(data.get('phone'),data.get('code')))
            if p=='/api/auth/register' and method=='POST':return self.respond(m.register_password(data.get('phone'),data.get('password'),data.get('nickname')))
            if p=='/api/auth/recover' and method=='POST':return self.respond(m.recover_password(data.get('phone'),data.get('recovery_code'),data.get('new_password')))
            if p=='/api/products' and method=='GET':return self.respond(m.products(self.optional_user(),query))
            if p=='/api/product' and method=='GET':return self.respond(m.product(int(query['id']),self.optional_user()))
            if p=='/api/profile' and method=='GET':
                who=int(query['id']);profile=m.profile(who)
                # 公开主页只给「资料」字段：role / status 属于账号治理信息，
                # 公开出去等于对外暴露某人是否被封禁或已注销。
                public={k:profile[k] for k in ('id','nickname','college','major','education','bio','score')}
                public['trusted']=m.trusted_map([who]).get(who,False)
                return self.respond({'user':public,'products':m.products(self.optional_user(),{'seller':str(who)})})
            if p=='/api/posts' and method=='GET':return self.respond(m.posts(query.get('topic',''),query.get('limit','20'),query.get('offset','0')))
            if p=='/api/comments' and method=='GET':return self.respond(m.comments(int(query['id']),query.get('before')))
            if p=='/api/wants' and method=='GET':return self.respond(m.wants(self.optional_user()))
            if p=='/api/want' and method=='GET':return self.respond(m.want(self.optional_user(),int(query['id'])))
            if p.startswith('/media/'):
                fid=p.split('/')[-1];upload=m.row('SELECT * FROM uploads WHERE id=?',(fid,));m.require(upload,'图片不存在',404)
                if upload['private']:
                    uid=self.uid();m.require(uid==upload['user_id'] or m.profile(uid)['role'] in ['admin','support'],'无权读取私密图片',403)
                else:
                    # 在售商品的图照常公开。商品一旦被下架、退款或封禁变成 removed，
                    # 只要还有订单快照引用这张图，交易双方仍要能看到，
                    # 否则「我的订单」里的商品缩略图会变成 403 裂图（订单存的是图片地址快照）。
                    needle='/media/'+fid
                    listed=bool(m.row("SELECT 1 FROM products WHERE status<>'removed' AND data LIKE ?",('%'+needle+'%',))) \
                        or bool(m.row("SELECT 1 FROM orders WHERE items LIKE ?",('%'+needle+'%',)))
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
            if p=='/api/auth/password' and method=='POST':return self.respond(m.change_password(u,data.get('old_password'),data.get('new_password')))
            if p=='/api/me':
                if method=='POST':return self.respond(m.update_profile(u,data))
                me=m.profile(u)
                # 个人页的「诚信客户」pill 读这个字段；它和商品卡上的标签
                # 必须来自同一套判定（发布≥10 + 至少1笔交付 + 全按时 + 无退款）。
                me['trusted']=m.trusted_map([u]).get(u,False)
                return self.respond(me)
            if p=='/api/auth/logout':m.logout(self.token());return self.respond({'ok':True})
            if p=='/api/auth/deactivate' and method=='POST':return self.respond(m.deactivate(u))
            if p=='/api/notifications':return self.respond(m.read_notifications(u,data.get('id') or None) if method=='POST' else m.notifications(u))
            if p=='/api/badges':return self.respond(m.badges(u))
            if p=='/api/wants' and method=='POST':return self.respond(m.create_want(u,data))
            if p=='/api/publish' and method=='POST':return self.respond(m.publish(u,data))
            if p=='/api/my-products':return self.respond(m.my_products(u,query.get('status')))
            if p=='/api/product/status' and method=='POST':return self.respond(m.set_product_status(u,int(data['id']),data['action']))
            if p=='/api/product/promote' and method=='POST':return self.respond(m.promote(u,int(data['id']),data.get('tier')))
            if p=='/api/product/moderate' and method=='POST':return self.respond(m.moderate_product(u,int(data['id']),data.get('action'),data.get('reason','')))
            if p=='/api/product/review' and method=='POST':return self.respond(m.review_product(u,int(data['id']),data.get('decision'),data.get('reason')))
            if p=='/api/product/removed' and method=='GET':return self.respond(m.removed_products(u))
            if p=='/api/user/dossier' and method=='GET':return self.respond(m.dossier(u,int(query['id'])))
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
            if p=='/api/ticket/resolve' and method=='POST':return self.respond(m.resolve_ticket(u,int(data['id']),data))
            # 历史工单补交易凭证：候选订单只返回当事人/所涉商品相关的那些，
            # 绑定后处理人才看得到金额、双方和交付记录，也才能据此扣信誉。
            if p=='/api/ticket/candidates':return self.respond(m.ticket_order_candidates(u,int(query['id'])))
            if p=='/api/ticket/link-order' and method=='POST':return self.respond(m.link_ticket_order(u,int(data['id']),int(data['order_id'])))
            if p=='/api/credit' and method=='POST':return self.respond(m.credit_action(u,int(data['target']),data.get('delta'),data['reason'],int(data['ticket_id']),data.get('violation'),bool(data.get('dry_run',False))))
            if p=='/api/credit/history':return self.respond(m.credit_history(u))
            if p=='/api/review' and method=='POST':return self.respond(m.review(u,int(data['order_id']),data['rating'],data['body']))
            if p=='/api/rooms':return self.respond(m.rooms(u))
            if p=='/api/rooms/join' and method=='POST':return self.respond(m.join_room(u,data['kind']))
            if p=='/api/rooms/private' and method=='POST':return self.respond(m.private_room(u,int(data['peer'])))
            if p=='/api/support/room' and method=='POST':return self.respond(m.support_room(u,data.get('ticket_id')))
            if p=='/api/support/claim' and method=='POST':return self.respond(m.claim_support_room(u,int(data['room_id']),data.get('action','claim')))
            if p=='/api/messages':return self.respond(m.send_message(u,int(data['room_id']),data['body'],data['key']) if method=='POST' else m.messages(u,int(query['room_id']),int(query.get('after',0))))
            if p=='/api/messages/recall' and method=='POST':return self.respond(m.recall_message(u,int(data['message_id'])))
            # 仅自己删除：只从我的聊天记录里移除，对方仍可见。
            if p=='/api/messages/hide' and method=='POST':return self.respond(m.hide_message(u,int(data['message_id'])))
            if p=='/api/room/members':return self.respond(m.room_members(u,int(query['room_id'])))
            if p=='/api/block' and method=='POST':return self.respond(m.block(u,int(data['target']),bool(data.get('enabled',True))))
            if p=='/api/posts' and method=='POST':return self.respond(m.add_post(u,data))
            if p=='/api/comments' and method=='POST':return self.respond(m.comment(u,int(data['post_id']),data['body'],int(data.get('parent_id') or 0)))
            if p=='/api/moderate' and method=='POST':return self.respond(m.moderate(u,data))
            if p=='/api/nominate' and method=='POST':return self.respond(m.nominate(u,data))
            if p=='/api/admin':
                m.staff(u);return self.respond({'users':m.rows('SELECT id,nickname,college,score,role,status FROM users'),'audit':m.audit_log(u,limit=100),'nominations':m.rows('SELECT n.*,u.nickname,r.name FROM nominations n JOIN users u ON u.id=n.user_id JOIN rooms r ON r.id=n.room_id')})
            if p=='/api/audit' and method=='GET':
                return self.respond(m.audit_log(u,kind=query.get('type',''),actor=query.get('actor'),
                                                since=query.get('since'),until=query.get('until'),
                                                limit=query.get('limit',200)))
            if p=='/api/audit/export' and method=='GET':
                body=m.audit_csv(u,kind=query.get('type',''),actor=query.get('actor'),
                                 since=query.get('since'),until=query.get('until'))
                return self.respond(body,kind='text/csv; charset=utf-8')
            if p=='/api/admin/staff' and method=='GET':return self.respond(m.staff_accounts(u))
            # 全量注册账号（管理员/开发者）：用于把普通同学提成客服、查某人有没有注册。
            if p=='/api/admin/accounts' and method=='GET':return self.respond(m.all_accounts(u,query.get('q','')))
            if p=='/api/admin/staff' and method=='POST':return self.respond(m.create_staff(u,data))
            if p=='/api/admin/staff/status' and method=='POST':return self.respond(m.set_staff_status(u,int(data['id']),data.get('status')))
            if p=='/api/admin/staff/password' and method=='POST':return self.respond(m.reset_staff_password(u,int(data['id'])))
            if p=='/api/admin/role' and method=='POST':return self.respond(m.change_role(u,data))
            if p=='/api/admin/session/revoke' and method=='POST':return self.respond(m.revoke_sessions(u,int(data['id'])))
            if p=='/api/admin/sellers' and method=='GET':return self.respond(m.sellers(u))
            if p=='/api/admin/seller/delist' and method=='POST':return self.respond(m.moderate_seller(u,int(data['seller_id']),data.get('reason','')))
            if p=='/api/admin/content' and method=='GET':return self.respond(m.flagged_content(u))
            if p=='/api/admin/content/action' and method=='POST':return self.respond(m.content_action(u,data.get('kind'),int(data['id']),data.get('action','remove'),data.get('reason','')))
            if p=='/api/moderation/words' and method=='GET':return self.respond(m.moderation_words(u))
            if p=='/api/moderation/words' and method=='POST':
                op=data.get('op')
                if op=='add':return self.respond(m.add_moderation_word(u,data))
                if op=='remove':return self.respond(m.remove_moderation_word(u,data.get('word')))
                if op=='restore':return self.respond(m.restore_moderation_word(u,data.get('word')))
                raise DomainError('不支持的操作')
            if p=='/api/admin/nominate' and method=='POST':
                m.require(m.profile(u)['role']=='admin','仅平台管理员可任命',403)
                with m.tx() as c:
                    n=c.execute("SELECT * FROM nominations WHERE id=? AND status='pending'",(int(data['id']),)).fetchone();m.require(n,'申请不存在或已处理')
                    c.execute("UPDATE nominations SET status='approved' WHERE id=?",(n['id'],));c.execute("UPDATE members SET role='moderator' WHERE room_id=? AND user_id=?",(n['room_id'],n['user_id']))
                    c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,n['user_id'],'appointment','群管理员申请审核通过',time.time()))
                return self.respond({'ok':True})
            if p=='/api/admin/ban' and method=='POST':return self.respond(m.ban_user(u,int(data['target']),bool(data.get('banned',True)),data.get('reason','')))
            if p=='/api/admin/stars' and method=='POST':return self.respond(m.adjust_stars(u,int(data['target']),int(data['delta']),data.get('reason','')))
            # 开发者清除账号：匿名化并释放手机号，本人可用原号重新注册。
            if p=='/api/admin/purge' and method=='POST':return self.respond(m.purge_account(u,int(data['target']),data.get('reason','')))
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
        # https 是正式部署的要求；--lan 局域网联调允许 http，但仅限 --trial。
        bad_scheme = parsed.scheme!='https' and not (trial and parsed.scheme=='http')
        if bad_scheme or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('公网地址必须是完整HTTPS源地址，不含路径或账号密码（--trial 局域网调试可用 http）')
    if host not in ['127.0.0.1','localhost'] and not public_origin:raise ValueError('公网绑定前需配置HUALI_PUBLIC_ORIGIN并通过HTTPS代理访问')
    market=Market(root,trial=trial)
    if admin:market.bootstrap_admin(*admin)
    server=Server((host,port),Handler);server.market=market;server.public_origin=public_origin;server.trust_proxy=trust_proxy;server.rates={};server.rate_lock=threading.Lock()
    server.web=Path(web).resolve() if web else WEB
    if seed:seed_data(server.market)
    return server

def lan_ip():
    """取本机局域网 IPv4，供 --lan 自动推导 public-origin 与打印访问地址。

    直接连 8.8.8.8 取出口 IP 在开 VPN 时会拿到 198.18.x（虚拟网卡），别人的电脑打不开。
    这里枚举全部本机地址后按「192.168 > 10.x > 172.16-31」排序，
    并排除回环、169.254 与 198.18/198.19 基准测试段（VPN 常用）。
    """
    candidates=set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            candidates.add(info[4][0])
    except OSError:pass
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8',80));candidates.add(s.getsockname()[0])
        finally:s.close()
    except OSError:pass
    def rank(ip):
        try:a=ipaddress.IPv4Address(ip)
        except ValueError:return -1
        if a.is_loopback or a.is_link_local or a.is_multicast:return -1
        if ip.startswith(('198.18.','198.19.')):return -1
        if not a.is_private:return -1
        if ip.startswith('192.168.'):return 3
        if ip.startswith('10.'):return 2
        return 1
    for ip in sorted(candidates,key=lambda x:(-rank(x),x)):
        if rank(ip)>0:return ip
    return '127.0.0.1'


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')))
    ap.add_argument('--data',default=os.environ.get('HUALI_DATA_DIR'))
    ap.add_argument('--no-seed',action='store_true')
    ap.add_argument('--trial',action='store_true')
    ap.add_argument('--host',default='127.0.0.1')
    ap.add_argument('--public-origin',default=os.environ.get('HUALI_PUBLIC_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL'))
    ap.add_argument('--trust-proxy',action='store_true')
    ap.add_argument('--web',default=os.environ.get('HUALI_WEB_DIR'))
    # --lan：学院试用想让同学用自己的电脑/手机访问时用。
    # 这行原本和上面挤在一起、超过 512 字节，Python 3.8 在 Windows 上按块
    # 读源码时会把中文 help 文本切成半个字符，直接报 Non-UTF-8 起不来。
    ap.add_argument('--lan',action='store_true',help='开放局域网访问（仅 --trial）：自动绑定 0.0.0.0 并推导 public-origin')
    args=ap.parse_args()
    # --lan：学院试用想让同学用自己的电脑/手机访问时用。
    # 只放开监听与 Origin 校验，不改任何业务规则；演示模式仍只允许本机。
    if args.lan:
        if not args.trial:ap.error('--lan 只在 --trial 试用模式下可用（演示模式仅允许本机访问）')
        args.host='0.0.0.0'
        if not args.public_origin:args.public_origin='http://%s:%d'%(lan_ip(),args.port)
    root=args.data or data_dir(args.trial)
    phone=os.environ.get('HUALI_ADMIN_PHONE');password=os.environ.get('HUALI_ADMIN_PASSWORD')
    if bool(phone)!=bool(password):ap.error('管理员手机号与密码必须同时配置，或均不配置')
    if phone and not args.trial:ap.error('管理员初始化仅供--trial模式使用')
    try:server=make_server(root,args.port,not args.trial and not args.no_seed,trial=args.trial,host=args.host,public_origin=args.public_origin,trust_proxy=args.trust_proxy,admin=(phone,password) if phone else None,web=args.web)
    except (DomainError,ValueError) as error:ap.error(str(error))
    if args.trial and not phone:
        # 学院试用版默认不 seed 任何账号，客服/群管理/信誉调整会无人可用。
        # 这里自动补一个管理员：号码固定，密码**每次部署随机生成**，
        # 只打印一次并写入数据目录（该文件在 .gitignore 里，不进仓库）。
        # 历史版本把固定口令写死在源码与前端一键按钮里，仓库又是公开的，
        # 等于任何人都能拿到管理员身份——不再提供默认共享密码。
        auto_phone='19065322759'
        created=not server.market.row('SELECT 1 FROM users WHERE phone=?',(auto_phone,))
        try:
            if not created:
                print(f'管理员 {auto_phone} 已存在，未重复创建；忘记密码可用 manage_trial.py 处理',flush=True)
            else:
                auto_password=secrets.token_urlsafe(12)
                server.market.bootstrap_admin(auto_phone,auto_password)
                hint=server.market.root/'admin-initial-password.txt'
                hint.write_text(f'管理员手机号：{auto_phone}\n初始密码：{auto_password}\n'
                                f'首次登录后请在「我的 → 修改密码」改掉，改完可删除本文件。\n',encoding='utf-8')
                print(f'已创建管理员：手机号 {auto_phone}',flush=True)
                print(f'初始密码：{auto_password}',flush=True)
                print(f'（同一份也写到了 {hint}，该文件不入库；也可用 HUALI_ADMIN_PHONE/HUALI_ADMIN_PASSWORD 指定）',flush=True)
        except DomainError as error:
            # 号码已被注册成普通账号时不能自动提权（防越权校验拦截）。
            # 不能因此让整个服务起不来——提示运营者手动处理即可。
            print(f'自动创建管理员跳过：{error}',flush=True)
            print('如需把该号码升级为管理员，请直接在数据库中将其 users.role 改为 admin。',flush=True)
    def timer():
        while True:
            try:
                server.market.tick()
                backups=list((server.market.root/'backups').glob('*.zip')) if (server.market.root/'backups').exists() else []
                if not backups or time.time()-max(x.stat().st_mtime for x in backups)>86400:server.market._backup()
            except Exception:traceback.print_exc()
            time.sleep(30)
    threading.Thread(target=timer,daemon=True).start()
    mode='计算机学院试用版 · 手机号密码登录 · 模拟交易' if args.trial else '本地模拟版'
    print(f'华立转角 · {mode} · port {server.server_port} · Ctrl+C停止',flush=True)
    if args.lan:
        print(f'局域网访问：http://{lan_ip()}:{server.server_port}',flush=True)
        print('同一 WiFi 的手机/其他电脑可直接打开；连不上先检查 Windows 防火墙是否放行该端口。',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
