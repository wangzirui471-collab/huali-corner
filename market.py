import time, json, re, secrets, hashlib, io, sqlite3, zipfile, tempfile
from contextlib import closing, nullcontext
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from db import Store
from community import Community
from auth import PasswordAuth
from publishing import Publishing
from operations import Operations
from notifications import Notifications

class DomainError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

class Market(Store,Community,PasswordAuth,Publishing,Operations,Notifications):
    @staticmethod
    def require(ok,message,status=400):
        if not ok:raise DomainError(message,status)
    @staticmethod
    def text(v,maxlen,label):
        Market.require(isinstance(v,str) and 0<len(v.strip())<=maxlen,f'{label}需填写且不超过{maxlen}字')
        return v.strip()
    @staticmethod
    def cents(v,label='金额'):
        Market.require(type(v) is int and 0<=v<=1000000,f'{label}须为0至10000元之间的整数分');return v
    def __init__(self,root,trial=False):
        self.trial=trial;super().__init__(root)
        with self.tx() as c:
            mode='trial' if trial else 'demo';previous=c.execute("SELECT value FROM settings WHERE key='auth_mode'").fetchone()
            self.require(not previous or previous['value']==mode,'演示和学院试用必须使用不同的数据目录',409)
            self.require(previous or not trial or not c.execute('SELECT 1 FROM users LIMIT 1').fetchone(),'旧演示数据不能用作试用账号库，请指定新的数据目录',409)
            c.execute("INSERT OR IGNORE INTO settings VALUES('auth_mode',?)",(mode,))
            for upload in c.execute('SELECT id,path FROM uploads').fetchall():
                local=self.root/'uploads'/Path(upload['path']).name
                if local.exists():c.execute('UPDATE uploads SET path=? WHERE id=?',(str(local),upload['id']))
            for phone,nick,role in ([] if trial else [('13800000001','林同学','user'),('13800000002','小陈同学','user'),('13800000003','转角客服','admin')]):
                c.execute('INSERT OR IGNORE INTO users(phone,nickname,role,major) VALUES(?,?,?,?)',(phone,nick,role,'计算机科学与技术'))
    def request_code(self,phone):
        self.require(not self.trial,'学院试用采用密码登录，测试验证码已关闭',403)
        self.require(isinstance(phone,str) and re.fullmatch(r'1[3-9]\d{9}',phone),'请输入11位手机号')
        code=str(secrets.randbelow(900000)+100000)
        with self.tx() as c:c.execute('INSERT OR REPLACE INTO otp VALUES(?,?,?,0)',(phone,hashlib.sha256(code.encode()).hexdigest(),time.time()+300))
        return {'demo_code':code,'simulation':True,'message':'本地测试验证码，不会发送短信'}
    def login(self,phone,code):
        self.require(not self.trial,'学院试用采用密码登录，测试验证码已关闭',403)
        with self.tx() as c:
            r=c.execute('SELECT * FROM otp WHERE phone=?',(phone,)).fetchone()
            valid=r and r['expires']>time.time() and r['attempts']<5 and secrets.compare_digest(r['digest'],hashlib.sha256(str(code).encode()).hexdigest())
            if not valid:
                if r:c.execute('UPDATE otp SET attempts=attempts+1 WHERE phone=?',(phone,))
                c.commit();raise DomainError('验证码错误、过期或已使用',401)
            c.execute('DELETE FROM otp WHERE phone=?',(phone,))
            c.execute('INSERT OR IGNORE INTO users(phone,nickname) VALUES(?,?)',(phone,'同学'+phone[-4:]))
            uid=c.execute('SELECT id FROM users WHERE phone=?',(phone,)).fetchone()[0]
            token=secrets.token_urlsafe(32)
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400*7))
        return {'token':token,'user':self.profile(uid),'simulation':True}
    def user(self,token):
        r=self.row('SELECT s.user_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.is_active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time()))
        self.require(r,'请先登录',401);return r['user_id']
    def logout(self,token):
        with self.tx() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def profile(self,u):
        r=self.row('SELECT id,nickname,college,major,education,bio,role,score FROM users WHERE id=?',(u,))
        self.require(r,'用户不存在',404);return r
    def update_profile(self,u,d):
        nickname=self.text(d.get('nickname'),24,'昵称');college='计算机工程学院' if self.trial else str(d.get('college',''))[:80];major=str(d.get('major',''))[:80]
        education=d.get('education','本科');self.require(education in ['本科','专科','已毕业','其他'],'暂不开放该层次')
        with self.tx() as c:c.execute('UPDATE users SET nickname=?,college=?,major=?,education=?,bio=? WHERE id=?',(nickname,college,major,education,str(d.get('bio',''))[:300],u))
        return self.profile(u)
    def staff(self,u):self.require(self.profile(u)['role'] in ['admin','support'],'仅客服或管理员可操作',403)
    def add_upload(self,u,content,angle,private=False):
        self.require(angle in ['front','side','top','extra','proof'],'图片角度不正确')
        self.require(0<len(content)<=5*1024*1024,'单张图片需小于5MB')
        try:
            with Image.open(io.BytesIO(content)) as im:
                self.require(im.width*im.height<=20000000,'图片尺寸过大')
                im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1600,1600))
                out=io.BytesIO();im.save(out,'WEBP',quality=85)
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):raise DomainError('请上传有效的JPEG/PNG/WebP图片')
        digest=hashlib.sha256(out.getvalue()).hexdigest();fid=secrets.token_hex(16)
        path=self.root/'uploads'/(fid+'.webp');path.write_bytes(out.getvalue())
        with self.tx() as c:c.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?)',(fid,u,str(path),digest,angle,int(private)))
        return {'id':fid,'url':'/media/'+fid,'angle':angle,'private':private}
    def publish(self,u,d,*,connection=None,stock_key=None,source_draft_id=None):
        self.require(self.profile(u)['score']>=60,'信誉分低于60，暂不能发布；可在客服中心申诉',403)
        self.require(not self.row('SELECT trading_blocked FROM users WHERE id=?',(u,))['trading_blocked'],'当前账号已限制新交易，可申请申诉',403)
        title=self.text(d.get('title'),80,'标题');description=self.text(d.get('description'),3000,'商品介绍')
        self.require(d.get('category') in ['books','living','sports'],'请选择二手书、宿舍生活或运动闲置')
        price=self.cents(d.get('price'));fee=self.cents(d.get('delivery_fee',0),'送货费')
        delivery=d.get('delivery','pickup');self.require(delivery in ['pickup','delivery','both'],'请选择交付方式')
        region=self.text(d.get('region'),80,'自提/送货区域')
        ids=d.get('photos',[]);self.require(isinstance(ids,list) and 3<=len(ids)<=9 and len(set(ids))==len(ids),'需要三张不同角度实拍图，最多九张')
        photos=[self.row('SELECT * FROM uploads WHERE id=?',(i,)) for i in ids]
        self.require(all(p and p['user_id']==u and not p['private'] for p in photos),'只能使用本人上传的公开商品图')
        self.require({'front','side','top'}.issubset({p['angle'] for p in photos}),'请补齐正面、侧面和顶部照片')
        self.require(len({p['digest'] for p in photos})==len(photos),'重复图片不能凑数')
        if d['category']=='books':
            for k,label in [('edition','版次'),('publisher','出版社'),('notes','笔记情况'),('missing','缺页情况'),('accessories','附件情况')]:self.text(d.get(k),100,label)
        clean={k:d.get(k,'') for k in ['edition','publisher','notes','missing','accessories','bought','condition','author','isbn','course','major','college']}
        clean['description']=description;clean['photos']=[{'id':p['id'],'url':'/media/'+p['id'],'angle':p['angle']} for p in photos]
        proof=d.get('proof')
        if proof:
            pr=self.row('SELECT * FROM uploads WHERE id=?',(proof,));self.require(pr and pr['user_id']==u and pr['private'],'凭证无效');clean['proof']=proof
        clean['original_price']=self.cents(d.get('original_price',0),'原价');clean['simulation']=False
        with (self.tx() if connection is None else nullcontext(connection)) as c:
            pid=c.execute('INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created,stock_key,source_draft_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u,title,d['category'],price,fee,delivery,region,json.dumps(clean,ensure_ascii=False),time.time(),stock_key or secrets.token_hex(16),source_draft_id)).lastrowid
        return {'id':pid}
    def product(self,p,u=None):
        r=self.row('SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?',(p,))
        self.require(r,'商品不存在',404)
        data=json.loads(r.pop('data'));data.pop('proof',None);r.update(data)
        r['likes']=self.row("SELECT COUNT(*) n FROM reactions WHERE product_id=? AND kind='like'",(p,))['n']
        r['liked']=bool(u and self.row("SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='like'",(p,u)))
        r['favorited']=bool(u and self.row("SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='favorite'",(p,u)))
        return r
    def products(self,u=None,filters=None):
        f=filters or {};ids=self.rows('SELECT id FROM products ORDER BY id DESC');result=[]
        for row in ids:
            p=self.product(row['id'],u)
            if p['status']=='removed':continue
            if f.get('seller') and p['seller_id']!=int(f['seller']):continue
            if f.get('category') and p['category']!=f['category']:continue
            if f.get('favorite') and not p['favorited']:continue
            if f.get('q') and str(f['q']).lower() not in (' '.join(str(p.get(k,'')) for k in ['title','description','isbn','publisher','major','edition'])).lower():continue
            if f.get('available') and p['status']!='available':continue
            result.append(p)
        if f.get('sort')=='price':result.sort(key=lambda p:p['price']+(p['delivery_fee'] if p['delivery']=='delivery' else 0))
        return result[:100]
    def react(self,u,p,kind,on):
        self.product(p);self.require(kind in ['like','favorite'],'无效操作')
        with self.tx() as c:
            if on:c.execute('INSERT OR IGNORE INTO reactions VALUES(?,?,?)',(u,p,kind))
            else:c.execute('DELETE FROM reactions WHERE user_id=? AND product_id=? AND kind=?',(u,p,kind))
        return self.product(p,u)
    def offer(self,u,p,amount):
        item=self.product(p);self.cents(amount)
        self.require(item['seller_id']!=u and item['status']=='available','当前商品不能出价')
        with self.tx() as c:oid=c.execute('INSERT INTO offers(product_id,buyer_id,amount,created) VALUES(?,?,?,?)',(p,u,amount,time.time())).lastrowid
        return {'id':oid}
    def offers(self,u):
        return self.rows('SELECT o.*,p.title,p.seller_id,u.nickname FROM offers o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id WHERE o.buyer_id=? OR p.seller_id=? ORDER BY o.id DESC',(u,u))
    def accept_offer(self,u,oid,accept):
        with self.tx() as c:
            r=c.execute('SELECT o.*,p.seller_id FROM offers o JOIN products p ON p.id=o.product_id WHERE o.id=?',(oid,)).fetchone()
            self.require(r and r['seller_id']==u,'不能处理他人报价',403)
            c.execute('UPDATE offers SET status=? WHERE id=?',('accepted' if accept else 'rejected',oid))
        return {'ok':True}
    def checkout(self,u,d):
        self.require(not self.row('SELECT trading_blocked FROM users WHERE id=?',(u,))['trading_blocked'],'当前账号已限制新交易，可申请申诉',403)
        ids=d.get('product_ids');self.require(isinstance(ids,list) and 1<=len(ids)<=20 and len(set(ids))==len(ids),'请选择1至20件不同商品')
        key=self.text(d.get('key'),100,'请求标识');delivery=d.get('delivery');self.require(delivery in ['pickup','delivery'],'交付方式错误')
        try:appointment=float(d.get('appointment',0))
        except (ValueError,TypeError):raise DomainError('交付时间无效')
        self.require(time.time()+60<appointment<time.time()+86400*30,'请选择未来30天内的交付时间')
        address=self.text(d.get('address'),150,'收货公共地点') if delivery=='delivery' else ''
        with self.tx() as c:
            old=c.execute('SELECT id FROM orders WHERE buyer_id=? AND request_key=?',(u,key)).fetchone()
            if old:return self.order(u,old['id'])
            products=[c.execute('SELECT * FROM products WHERE id=?',(i,)).fetchone() for i in ids]
            self.require(all(products),'商品不存在')
            self.require(len({p['seller_id'] for p in products})==1,'只能合并同一卖家的商品')
            seller=products[0]['seller_id'];self.require(seller!=u,'不能购买自己的商品')
            self.require(all(p['status']=='available' for p in products),'部分商品已被预留或售出',409)
            self.require(all(p['delivery'] in [delivery,'both'] for p in products),'商品不支持所选交付方式')
            items=[]
            for p in products:
                price=p['price'];offer=c.execute("SELECT amount FROM offers WHERE product_id=? AND buyer_id=? AND status='accepted' ORDER BY id DESC LIMIT 1",(p['id'],u)).fetchone()
                if offer:price=offer['amount']
                data=json.loads(p['data']);items.append({'id':p['id'],'title':p['title'],'price':price,'region':p['region'],'edition':data.get('edition',''),'notes':data.get('notes',''),'missing':data.get('missing',''),'accessories':data.get('accessories',''),'photo':data['photos'][0]['url']})
            subtotal=sum(p['price'] for p in items);fee=max(p['delivery_fee'] for p in products) if delivery=='delivery' else 0
            oid=c.execute('INSERT INTO orders(buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,appointment,status,created,request_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(u,seller,json.dumps(items,ensure_ascii=False),subtotal,fee,subtotal+fee,delivery,address,appointment,'awaiting_payment',time.time(),key)).lastrowid
            for p in products:c.execute("UPDATE products SET status='reserved' WHERE id=?",(p['id'],))
            self.notify(c,[seller],f'order:{oid}:created','有新订单，等待买家模拟付款','order',oid)
        return self.order(u,oid)
    def order(self,u,oid):
        r=self.row('SELECT * FROM orders WHERE id=?',(oid,));self.require(r,'订单不存在',404)
        self.require(u in [r['buyer_id'],r['seller_id']] or self.profile(u)['role'] in ['support','admin'],'不能查看他人订单',403)
        r['items']=json.loads(r['items']);r['ledger']=self.rows('SELECT kind,amount,created FROM ledger WHERE order_id=? ORDER BY id',(oid,))
        r['changes']=self.rows('SELECT * FROM order_changes WHERE order_id=? ORDER BY id DESC',(oid,))
        r['buyer']=self.profile(r['buyer_id'])['nickname'];r['seller']=self.profile(r['seller_id'])['nickname'];return r
    def orders(self,u):return [self.order(u,r['id']) for r in self.rows('SELECT id FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC',(u,u))]
    def journal(self,c,oid,kind,amount):c.execute('INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',(oid,kind,amount,time.time()))
    def release(self,c,r):
        for p in json.loads(r['items']):c.execute("UPDATE products SET status='available' WHERE id=?",(p['id'],))
    def complete(self,c,r,now):
        c.execute("UPDATE orders SET status='completed',completed_at=? WHERE id=?",(now,r['id']))
        self.journal(c,r['id'],'settlement',r['total'])
        for p in json.loads(r['items']):c.execute("UPDATE products SET status='sold' WHERE id=?",(p['id'],))
        self.notify(c,[r['buyer_id'],r['seller_id']],f"order:{r['id']}:completed",'订单已确认收货并完成模拟结算','order',r['id'])
    def order_action(self,u,oid,action,d):
        with self.tx() as c:
            r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();self.require(r,'订单不存在',404)
            self.require(u in [r['buyer_id'],r['seller_id']],'不能处理他人订单',403)
            buyer=u==r['buyer_id'];now=time.time();status=r['status']
            if action=='pay':
                self.require(buyer,'仅买家可付款',403)
                if status=='awaiting_payment':
                    self.require(now-r['created']<1800,'订单付款已超时')
                    c.execute("UPDATE orders SET status='paid',paid_at=? WHERE id=?",(now,oid));self.journal(c,oid,'payment',r['total'])
                    self.notify(c,[r['seller_id']],f'order:{oid}:paid','买家已模拟付款，请确认交付安排','order',oid)
                else:self.require(status in ['paid','awaiting_handover','awaiting_receipt','completed'],'当前不可支付')
            elif action=='cancel':
                self.require(buyer,'仅买家可取消',403)
                self.require(status in ['awaiting_payment','paid','cancelled'],'已交付或存在争议，请申请售后')
                if status!='cancelled':
                    if status=='paid':self.journal(c,oid,'refund',r['total'])
                    c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(oid,));self.release(c,r)
                    self.notify(c,[r['seller_id']],f'order:{oid}:cancelled','买家已取消订单','order',oid)
            elif action=='deliver':
                self.require(not buyer and status=='paid','仅卖家可在付款后标记交付')
                c.execute("UPDATE orders SET status='awaiting_handover',schedule_confirmed=1,delivered_at=? WHERE id=?",(now,oid))
                self.notify(c,[r['buyer_id']],f'order:{oid}:delivered','卖家已标记交付，请核对实物','order',oid)
            elif action=='handover':
                self.require(buyer and status=='awaiting_handover','请在实际交接后确认')
                c.execute("UPDATE orders SET status='awaiting_receipt',handover_at=? WHERE id=?",(now,oid))
                self.notify(c,[r['seller_id']],f'order:{oid}:handover','买家已确认实物交接','order',oid)
            elif action=='receive':
                self.require(buyer and status in ['awaiting_handover','awaiting_receipt','completed'],'当前不能确认收货')
                if status!='completed':self.complete(c,r,now)
            elif action=='confirm_schedule':
                self.require(not buyer and status=='paid','仅卖家可在付款后确认时间')
                c.execute('UPDATE orders SET schedule_confirmed=1 WHERE id=?',(oid,))
                self.notify(c,[r['buyer_id']],f'order:{oid}:scheduled','卖家已确认交付时间','order',oid)
            elif action=='reschedule':
                self.require(status in ['paid','awaiting_handover'],'当前不能申请改约')
                appointment=d.get('appointment');self.require(type(appointment) in [int,float] and now+60<appointment<now+86400*30,'请选择未来30天内的改约时间')
                address=self.text(d.get('address') or r['address'] or json.loads(r['items'])[0]['region'],150,'改约地点')
                self.require(not c.execute("SELECT 1 FROM order_changes WHERE order_id=? AND status='pending'",(oid,)).fetchone(),'已有待对方确认的改约')
                change_id=c.execute('INSERT INTO order_changes(order_id,proposer,appointment,address,created) VALUES(?,?,?,?,?)',(oid,u,appointment,address,now)).lastrowid
                self.notify(c,[r['seller_id'] if buyer else r['buyer_id']],f'change:{change_id}:proposed','对方申请改约，请确认新的时间和地点','order',oid)
            else:raise DomainError('不支持此订单操作')
        return self.order(u,oid)
    def respond_change(self,u,change_id,accept):
        with self.tx() as c:
            change=c.execute('SELECT * FROM order_changes WHERE id=?',(change_id,)).fetchone();self.require(change,'改约不存在',404)
            o=c.execute('SELECT * FROM orders WHERE id=?',(change['order_id'],)).fetchone()
            self.require(u in [o['buyer_id'],o['seller_id']] and u!=change['proposer'],'仅交易另一方可确认改约',403)
            self.require(o['status'] in ['paid','awaiting_handover'] and change['status']=='pending','改约已失效')
            self.require(change['appointment']>time.time()+60 or not accept,'该时段已过期')
            if accept:c.execute('UPDATE orders SET appointment=?,address=?,schedule_confirmed=1 WHERE id=?',(change['appointment'],change['address'],o['id']))
            self.notify(c,[change['proposer']],f'change:{change_id}:answered','对方已'+('接受' if accept else '拒绝')+'改约','order',o['id'])
            c.execute('UPDATE order_changes SET status=? WHERE id=?',('accepted' if accept else 'rejected',change_id))
        return {'ok':True}
    def tick(self,now=None):
        now=now or time.time()
        with self.tx() as c:
            for r in c.execute("SELECT * FROM orders WHERE status='awaiting_payment' AND created<?",(now-1800,)).fetchall():
                c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],));self.release(c,r)
                self.notify(c,[r['buyer_id'],r['seller_id']],f"order:{r['id']}:expired",'订单已超时取消；已模拟付款的金额自动模拟退回','order',r['id'])
            for r in c.execute("SELECT * FROM orders WHERE status='paid' AND schedule_confirmed=0 AND created<?",(now-86400,)).fetchall():
                self.journal(c,r['id'],'refund',r['total']);c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],));self.release(c,r)
                self.notify(c,[r['buyer_id'],r['seller_id']],f"order:{r['id']}:expired",'订单已超时取消；已模拟付款的金额自动模拟退回','order',r['id'])
            for r in c.execute("SELECT * FROM orders WHERE status='awaiting_receipt' AND handover_at<?",(now-86400,)).fetchall():
                if not c.execute("SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected')",(r['id'],)).fetchone():self.complete(c,r,now)
    def create_ticket(self,u,d):
        typ=d.get('type','other');self.require(typ in ['refund','report','appeal','reschedule','other'],'工单类型错误')
        subject=self.text(d.get('subject'),80,'问题标题');body=self.text(d.get('body'),3000,'问题说明');oid=d.get('order_id') or None;pid=d.get('product_id') or None
        refund_mode=d.get('refund_mode','refund_only')
        self.require(refund_mode in ['refund_only','return_refund'],'退款方式无效')
        evidence=self.validate_evidence(u,d.get('evidence',[]))
        with self.tx() as c:
            if oid:
                r=c.execute('SELECT * FROM orders WHERE id=?',(int(oid),)).fetchone()
                self.require(r and u in [r['buyer_id'],r['seller_id']],'不能关联他人订单',403)
                if typ=='refund':
                    self.require(u==r['buyer_id'] and r['status'] in ['paid','awaiting_handover','awaiting_receipt','completed','disputed'],'订单当前不能申请退款')
                    self.require(not c.execute("SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected')",(oid,)).fetchone(),'已有待处理退款')
                    c.execute("UPDATE orders SET status='disputed' WHERE id=?",(oid,))
            else:self.require(typ!='refund','退款必须关联订单')
            if pid:self.product(int(pid))
            tid=c.execute('INSERT INTO tickets(user_id,order_id,product_id,type,subject,body,created) VALUES(?,?,?,?,?,?,?)',(u,oid,pid,typ,subject,body,time.time())).lastrowid
            c.execute('UPDATE tickets SET refund_mode=? WHERE id=?',(refund_mode,tid))
            self.save_evidence(c,tid,u,evidence,False)
            self.notify_ticket(c,tid,f'ticket:{tid}:created','有新的售后／反馈工单',actor=u,queue=True)
        return self.ticket(u,tid)
    def ticket(self,u,tid):
        r=self.row('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?',(tid,));self.require(r,'工单不存在',404)
        staff=self.profile(u)['role'] in ['support','admin'];allowed=r['user_id']==u
        if r['order_id']:
            o=self.row('SELECT buyer_id,seller_id FROM orders WHERE id=?',(r['order_id'],));allowed=allowed or u in [o['buyer_id'],o['seller_id']]
        self.require(allowed or staff,'不能查看他人工单',403)
        staff=staff and not allowed
        r['messages']=self.rows('SELECT m.*,u.nickname FROM ticket_messages m JOIN users u ON u.id=m.user_id WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY m.id',(tid,int(staff)))
        r['evidence']=[{'id':x['upload_id'],'url':'/media/'+x['upload_id'],'internal':bool(x['internal'])} for x in self.rows('SELECT upload_id,internal FROM ticket_evidence WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY created_at',(tid,int(staff)))]
        return r
    def tickets(self,u):
        if self.profile(u)['role'] in ['admin','support']:ids=self.rows('SELECT id FROM tickets ORDER BY id DESC')
        else:ids=self.rows('SELECT t.id FROM tickets t LEFT JOIN orders o ON o.id=t.order_id WHERE t.user_id=? OR o.seller_id=? OR o.buyer_id=? ORDER BY t.id DESC',(u,u,u))
        return [self.ticket(u,r['id']) for r in ids]
    def reply_ticket(self,u,tid,d):
        self.ticket(u,tid);internal=d.get('internal',False)
        self.require(type(internal) is bool,'内部备注状态必须为布尔值')
        if internal:self.staff(u)
        evidence=self.validate_evidence(u,d.get('evidence',[]))
        with self.tx() as c:
            message_id=c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',(tid,u,self.text(d.get('body') or ('补充图片证据' if evidence else ''),2000,'回复'),int(internal),time.time())).lastrowid
            self.save_evidence(c,tid,u,evidence,internal)
            self.notify_ticket(c,tid,f'ticket:{tid}:reply:{message_id}','工单有新的回复或材料',actor=u,internal=internal)
        return self.ticket(u,tid)
    def check_conflict(self,u,t):
        if t.get('product_id'):
            pid=t['product_id'];self.require(self.product(pid)['seller_id']!=u,'不能审核自己发布商品的投诉',403)
            for order in self.rows('SELECT items FROM orders WHERE buyer_id=? OR seller_id=?',(u,u)):
                self.require(not any(p['id']==pid for p in json.loads(order['items'])),'该商品交易与你存在利益冲突，请交其他人员审核',403)
        if t.get('order_id'):
            order=self.row('SELECT buyer_id,seller_id FROM orders WHERE id=?',(t['order_id'],))
            self.require(u not in [order['buyer_id'],order['seller_id']],'不能审核自己的交易',403)
    def resolve_ticket(self,u,tid,d):
        self.staff(u);t=self.ticket(u,tid);reason=self.text(d.get('reason'),1000,'处理依据')
        self.require(t['user_id']!=u,'不能审核自己提交的工单',403)
        self.check_conflict(u,t)
        with self.tx() as c:
            t=c.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
            if t['status']=='resolved':return {'ok':True}
            outcome=d.get('outcome','resolved');self.require(outcome in ['refund','reject','resolved','review','claim','request_refund'],'处理方式无效')
            if t['type']=='refund' and outcome in ['refund','reject','resolved']:
                self.require(self.profile(u)['role']=='admin','退款审批仅限平台管理员；客服请提交处理建议',403)
            self.require(not t['assignee'] or t['assignee']==u or self.profile(u)['role']=='admin','工单已由其他客服认领，请由管理员转派',409)
            if outcome=='claim':
                c.execute("UPDATE tickets SET assignee=?,status='processing' WHERE id=?",(u,tid))
            elif outcome=='review':c.execute("UPDATE tickets SET assignee=?,status='review',reason=? WHERE id=?",(u,reason,tid))
            elif outcome=='request_refund':
                self.require(t['type']=='refund' and t['order_id'],'只有售后工单可提交退款建议')
                order=c.execute('SELECT total FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                amount=self.cents(d.get('amount',order['total']))
                self.require(0<amount<=order['total'],'退款建议金额无效')
                c.execute("UPDATE tickets SET assignee=?,status='review',reason=?,requested_amount=? WHERE id=?",(u,reason,amount,tid))
            else:
                if t['order_id']:
                    r=c.execute('SELECT * FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                    self.require(u not in [r['buyer_id'],r['seller_id']],'不能审核自己的交易',403)
                    if outcome=='refund':
                        self.require(t['type']=='refund' and r['status']=='disputed','只有争议退款工单可以退款')
                        self.require(t['refund_mode']!='return_refund' or t['return_received_at'],'请先由卖家确认收到退回实物，再批准退款')
                        amount=self.cents(d.get('amount',r['total']));self.require(0<amount<=r['total'],'退款不能超过订单金额')
                        self.journal(c,r['id'],'refund',amount)
                        settled=c.execute("SELECT amount FROM ledger WHERE order_id=? AND kind='settlement'",(r['id'],)).fetchone()
                        if settled:self.journal(c,r['id'],'settlement_reversal',min(amount,settled['amount']))
                        elif amount<r['total']:self.journal(c,r['id'],'settlement',r['total']-amount)
                        c.execute("UPDATE orders SET status='refunded' WHERE id=?",(r['id'],))
                        # Refunded physical items are NOT automatically offered again.
                        for p in json.loads(r['items']):c.execute("UPDATE products SET status='removed' WHERE id=?",(p['id'],))
                    elif r['status']=='disputed' and t['type']=='refund':
                        prior='completed' if r['completed_at'] else 'awaiting_receipt' if r['handover_at'] else 'awaiting_handover' if r['delivered_at'] else 'paid'
                        c.execute('UPDATE orders SET status=? WHERE id=?',(prior,r['id']))
                c.execute("UPDATE tickets SET status='resolved',assignee=?,outcome=?,reason=? WHERE id=?",(u,outcome,reason,tid))
            c.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',(u,'ticket_'+outcome,reason,tid,time.time()))
            self.notify_ticket(c,tid,f'ticket:{tid}:{outcome}', '工单处理进度已更新',actor=u,internal=outcome in ['review','request_refund'])
        return {'ok':True}
    def credit_action(self,u,target,delta,reason,tid):
        self.staff(u)
        self.require(False,'自由调整分数已停用，请使用规则处罚、申诉冲回或整改恢复接口',410)
    def credit_history(self,u):
        return self.rows("SELECT id,delta,reason,ticket_id,created,rule_key,reversal_of,score_before,score_after FROM audit WHERE target=? AND type IN ('credit','credit_warning','credit_reversal','credit_recovery') ORDER BY id DESC",(u,))
    def review(self,u,oid,rating,body):
        o=self.order(u,oid);self.require(o['status']=='completed' and u in [o['buyer_id'],o['seller_id']],'完成真实有效订单后才能评价')
        self.require(type(rating) is int and 1<=rating<=5,'评分需1至5分')
        with self.tx() as c:
            c.execute('INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?) ON CONFLICT(order_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body',(oid,u,rating,self.text(body,500,'评价'),time.time()))
        return {'ok':True,'simulation':True}
    def reconcile(self,u):
        self.staff(u);result=[]
        for o in self.rows('SELECT id,total,status FROM orders ORDER BY id DESC'):
            amounts={r['kind']:r['amount'] for r in self.rows('SELECT kind,amount FROM ledger WHERE order_id=?',(o['id'],))}
            net=amounts.get('settlement',0)-amounts.get('settlement_reversal',0)
            held=amounts.get('payment',0)-amounts.get('refund',0)-net
            result.append({**o,'payment':amounts.get('payment',0),'refund':amounts.get('refund',0),'net_settlement':net,'held':held,'consistent':held>=0 and (o['status'] not in ['completed','refunded','cancelled'] or held==0),'simulation':True})
        return result
    def backup(self,u):
        self.staff(u);return self._backup()
    def _backup(self):
        directory=self.root/'backups';directory.mkdir(exist_ok=True);path=directory/f'market-{time.time_ns()}.zip'
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/'market.sqlite3'
            # SQLite's transaction context does not close the connection. Windows
            # requires every snapshot handle to be closed before temporary cleanup.
            with closing(self.connect()) as source,closing(sqlite3.connect(dbpath)) as dest:
                source.backup(dest)
            with closing(sqlite3.connect(dbpath)) as snapshot:
                uploads=snapshot.execute('SELECT path FROM uploads').fetchall()
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.write(dbpath,'market.sqlite3')
                for upload in uploads:
                    file=Path(upload[0]);archive.write(file,'uploads/'+file.name)
                archive.writestr('manifest.json',json.dumps({'simulation':True,'created':time.time(),'files':len(uploads),'restore':'Stop server. Extract SQLite and uploads to an empty data directory; uploads paths are rebound on startup.'}))
        return str(path)
