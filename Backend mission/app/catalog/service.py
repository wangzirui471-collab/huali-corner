"""商品模块：发布、三图校验、浏览筛选、收藏点赞、出价、下架与重新上架。"""
import hashlib, io, json, secrets, time
from PIL import Image, ImageOps, UnidentifiedImageError
from ..core.errors import ValidationMixin, DomainError
from ..moderation import scan_product, message_for, report_of

# 付费置顶档位：档位 -> (天数, 模拟价格·分)。低价非强制，免费商品自然下沉。
PROMOTE_TIERS={'1d':(1,100),'3d':(3,300),'7d':(7,500)}


class CatalogService(ValidationMixin):
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

    def publish(self,u,d):
        self.require(self.profile(u)['score']>=60,'信誉分低于60，暂不能发布；可在客服中心申诉',403)
        title=self.text(d.get('title'),80,'标题');description=self.text(d.get('description'),3000,'商品介绍')
        self.require(d.get('category') in ['books','living','sports','electronics'],'请选择二手书、宿舍生活、运动闲置或电子产品')
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
        # 违禁品与交易外流的自动审核（app/moderation）。
        # 高危（法定禁止 / 加微信这类明确外流指令）直接拦死；
        # 中危（平台限制类目 / 疑似联系方式）放行但打标，进工作台的人工待审队列。
        # 放在所有字段校验之后：先让用户看到「标题没填」这种具体问题，
        # 而不是一上来就被审核拦掉、搞不清到底是哪儿不对。
        report=scan_product(d)
        self.require(not report['blocked'],'不能发布：'+message_for(report),422)
        marked=report_of(report)
        if marked:clean['moderation']=marked
        with self.tx() as c:
            pid=c.execute('INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created) VALUES(?,?,?,?,?,?,?,?,?)',(u,title,d['category'],price,fee,delivery,region,json.dumps(clean,ensure_ascii=False),time.time())).lastrowid
        return {'id':pid,'moderation':{'action':report['action'],'message':message_for(report)} if marked else None}

    def product(self,p,u=None):
        r=self.row('SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?',(p,))
        self.require(r,'商品不存在',404)
        data=json.loads(r.pop('data'));data.pop('proof',None)
        moderation=data.pop('moderation',None);r.update(data)
        # 审核标记对外只暴露「是否在审」这一个布尔值，**不公开命中词**——
        # 公开了就等于把词表变成「哪个词会触发审核」的查询接口，等于教人绕过。
        # 卖家本人和工作台能看到具体命中了什么，便于申诉与处置。
        r['under_review']=bool(moderation and not moderation.get('reviewed'))
        if moderation and (u==r['seller_id'] or (u and self.profile(u)['role'] in ['support','admin'])):
            r['moderation']=moderation
        r['likes']=self.row("SELECT COUNT(*) n FROM reactions WHERE product_id=? AND kind='like'",(p,))['n']
        r['liked']=bool(u and self.row("SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='like'",(p,u)))
        r['favorited']=bool(u and self.row("SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind='favorite'",(p,u)))
        return r

    def products(self,u=None,filters=None):
        f=filters or {};ids=self.rows('SELECT id FROM products ORDER BY id DESC');result=[]
        for row in ids:
            p=self.product(row['id'],u)
            # 主页商品流只展示「在售」：已售出、已预订、已下架的一律不出现。
            if p['status']!='available':continue
            if f.get('seller') and p['seller_id']!=int(f['seller']):continue
            if f.get('category') and p['category']!=f['category']:continue
            if f.get('favorite') and not p['favorited']:continue
            q=str(f.get('q') or '').lower().split()
            if q:
                hay=' '.join(str(p.get(k,'')) for k in ['title','description','isbn','publisher','major','edition']).lower()
                if not all(word in hay for word in q):continue
            result.append(p)
        if f.get('sort')=='price':result.sort(key=lambda p:p['price']+(p['delivery_fee'] if p['delivery']=='delivery' else 0))
        # 置顶商品提到最前（稳定排序：置顶的组内仍保持上面的价格/最新顺序）。
        now=time.time();result.sort(key=lambda p:0 if (p.get('promoted_until') or 0)>now else 1)
        return result[:100]

    def my_products(self,u,status=None):
        """卖家自己的商品列表，含已下架。products() 会把 removed 过滤掉，
        而卖家需要在「我发布的」里看到自己下架掉的东西，所以单独走这里。"""
        result=[]
        for row in self.rows('SELECT id FROM products WHERE seller_id=? ORDER BY id DESC',(u,)):
            p=self.product(row['id'],u)
            if status and p['status']!=status:continue
            result.append(p)
        return result

    def refund_locked(self,c,pid):
        """该商品是否卷入过退款/争议订单。

        需求 §10.6：仅退款或部分退款时物品留在买家处，原卖家不再持有实物，
        不能自行恢复出售；退款直接置 removed 后卖家又能点「重新上架」，
        等于绕过了这条规则。凡是有争议或已退款订单引用过的商品，重新上架需客服复核。"""
        for r in c.execute("SELECT items FROM orders WHERE status IN ('refunded','disputed')").fetchall():
            if any(i['id']==pid for i in json.loads(r['items'])):return True
        return False

    def set_product_status(self,u,pid,action):
        """下架 / 重新上架。只允许在 available 与 removed 之间切换。
        已被预订(reserved)或已售出(sold)的商品不能下架 —— 它们已经挂在别人的订单上，
        下架会让那张订单指向一个消失的商品。下架会一并清掉未到期的置顶，
        否则重新上架时会带着旧的置顶时间直接跳到最前面。"""
        p=self.row('SELECT * FROM products WHERE id=?',(pid,))
        self.require(p,'商品不存在',404)
        self.require(p['seller_id']==u,'只能管理自己发布的商品',403)
        if action=='delist':
            self.require(p['status']=='available','只有「在售」的商品可以下架；已预订或已售出的不能下架')
            target='removed';clear_promote=True
        elif action=='relist':
            self.require(p['status']=='removed','只有「已下架」的商品可以重新上架')
            self.require(self.profile(u)['score']>=60,'信誉分低于60，暂不能重新上架；可在客服中心申诉',403)
            with self.connect() as c:
                self.require(not self.refund_locked(c,pid),'该商品曾发生退款或争议，需联系客服复核后才能重新上架',403)
            target='available';clear_promote=False
        else:raise DomainError('不支持的商品操作')
        with self.tx() as c:
            c.execute('UPDATE products SET status=?,promoted_until=? WHERE id=?',(target,0 if clear_promote else (p['promoted_until'] or 0),pid))
        return self.product(pid,u)

    def promote(self,u,pid,tier):
        """付费置顶：把自己的在售商品顶到首页/分类顶部，低价非强制。
        模拟支付（不扣真实款项）。未到期续期从当前到期时间累加，不吞剩余时长。"""
        self.require(tier in PROMOTE_TIERS,'置顶档位无效')
        days,price=PROMOTE_TIERS[tier]
        p=self.row('SELECT * FROM products WHERE id=?',(pid,))
        self.require(p,'商品不存在',404)
        self.require(p['seller_id']==u,'只能置顶自己发布的商品',403)
        self.require(p['status']=='available','只有「在售」的商品可以置顶')
        base=max(p['promoted_until'] or 0,time.time())
        until=base+days*86400
        with self.tx() as c:
            c.execute('UPDATE products SET promoted_until=? WHERE id=?',(until,pid))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,u,'promote',f'商品 #{pid} 置顶 {days} 天（模拟支付 ¥{price/100:.2f}）',time.time()))
        return {'id':pid,'tier':tier,'days':days,'price':price,'promoted_until':until,'simulation':True}

    def react(self,u,p,kind,on):
        item=self.product(p);self.require(kind in ['like','favorite'],'无效操作')
        self.require(item['status']!='removed','商品已下架，无法收藏或点赞')
        with self.tx() as c:
            if on:c.execute('INSERT OR IGNORE INTO reactions VALUES(?,?,?)',(u,p,kind))
            else:c.execute('DELETE FROM reactions WHERE user_id=? AND product_id=? AND kind=?',(u,p,kind))
        return self.product(p,u)

    def offer(self,u,p,amount):
        item=self.product(p);amount=self.cents(amount,'出价')
        self.require(item['seller_id']!=u and item['status']=='available','当前商品不能出价')
        self.require(0<amount<item['price'],'出价需低于商品价且不能为0')
        with self.tx() as c:oid=c.execute('INSERT INTO offers(product_id,buyer_id,amount,created) VALUES(?,?,?,?)',(p,u,amount,time.time())).lastrowid
        return {'id':oid}

    def offers(self,u):
        return self.rows('SELECT o.*,p.title,p.seller_id,u.nickname FROM offers o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id WHERE o.buyer_id=? OR p.seller_id=? ORDER BY o.id DESC',(u,u))

    def accept_offer(self,u,oid,accept):
        with self.tx() as c:
            r=c.execute('SELECT o.*,p.seller_id,p.status product_status FROM offers o JOIN products p ON p.id=o.product_id WHERE o.id=?',(oid,)).fetchone()
            self.require(r and r['seller_id']==u,'不能处理他人报价',403)
            self.require(r['status']=='pending','该报价已处理')
            if accept:self.require(r['product_status']=='available','商品已下架或售出，不能接受报价')
            c.execute('UPDATE offers SET status=? WHERE id=?',('accepted' if accept else 'rejected',oid))
        return {'ok':True}
