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
        而卖家需要在「我发布的」里看到自己下架掉的东西，所以单独走这里。

        已下架商品附带 relist_locked / lock_reason：前端据此把注定失败的
        「重新上架」按钮换成「申请客服复核」入口。锁定原因与 set_product_status
        relist 分支的三条 require 完全一致——按钮和闸门必须看同一份规则，
        否则就是「按钮能点、点了必挂」的死胡同。"""
        result=[]
        for row in self.rows('SELECT id FROM products WHERE seller_id=? ORDER BY id DESC',(u,)):
            p=self.product(row['id'],u)
            if status and p['status']!=status:continue
            if p['status']=='removed':
                p['relist_locked'],p['lock_reason']=self._relist_lock(p,u)
            result.append(p)
        return result

    def _relist_lock(self,p,u):
        """卖家能否自行重新上架；锁定时给一句人话原因，前端直接展示。"""
        if p.get('delisted_by'):return True,'平台处置下架，需客服复核'
        with self.connect() as c:
            if self.refund_locked(c,p['id']):return True,'卷入退款或争议，需客服复核'
        if (self.profile(u).get('score') or 0)<60:return True,'信誉分低于60，暂不能上架'
        return False,''

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
            # 这一句是「平台强制下架」能不能立住的关键：没有它，管理员刚下架，
            # 卖家点一下「重新上架」就绕过去了，处置等于白做。
            # delisted_by=0 表示卖家自己下架的，可以自行恢复；>0 表示平台处置，必须走申诉。
            self.require(not (p['delisted_by'] or 0),'该商品由平台处置下架，需在客服中心申诉后由客服恢复',403)
            self.require(self.profile(u)['score']>=60,'信誉分低于60，暂不能重新上架；可在客服中心申诉',403)
            with self.connect() as c:
                self.require(not self.refund_locked(c,pid),'该商品曾发生退款或争议，需联系客服复核后才能重新上架',403)
            target='available';clear_promote=False
        else:raise DomainError('不支持的商品操作')
        with self.tx() as c:
            current=c.execute('SELECT seller_id,status FROM products WHERE id=?',(pid,)).fetchone()
            self.require(current and current['seller_id']==u and current['status']==p['status'],'商品状态已变化，请刷新后重试',409)
            c.execute('UPDATE products SET status=?,promoted_until=? WHERE id=?',(target,0 if clear_promote else (p['promoted_until'] or 0),pid))
        return self.product(pid,u)

    def moderate_product(self,u,pid,action,reason):
        """平台处置商品：强制下架 / 恢复上架。

        为什么不复用卖家的 set_product_status：平台处置必须多做三件事，
        而这三件事每一件都是「处置」这件事成立的前提：

          1. 写审计 —— 谁在什么时候因为什么下架了哪件商品；
          2. 通知卖家 —— 否则卖家只会发现东西凭空消失，不知道该找谁；
          3. 记下 delisted_by —— 把「平台下架」和「卖家自己下架」区分开，
             被平台处置的商品卖家不能自行恢复。

        管理员可下架包括本人在内的在售商品；客服管理他人商品，
        客服本人商品走普通自主下架。恢复上架由客服/管理员在申诉工单
        复核后执行，全程写审计并通知卖家。
        """
        self.staff(u);reason=self.text(reason,500,'处置理由')
        p=self.row('SELECT * FROM products WHERE id=?',(pid,))
        self.require(p,'商品不存在',404)
        self.require(p['seller_id']!=u or (action=='delist' and self.is_admin(u)),'该操作不能用于自己发布的商品',403)
        if action=='delist':
            # 已预留/已售出的商品挂在别人的订单上，强行下架会让那张订单指向消失的商品。
            # 这类要走工单流程（退款时会置 removed）。
            self.require(p['status']=='available','只有在售商品可以强制下架；已预留或已售出的请通过工单处理')
        elif action=='restore':
            # 恢复上架是「把平台已经判过违规的商品放回市场」，属于改判。
            # 改判由申诉流程触发：卖家提交申诉工单，客服/管理员在工单里复核。
            # 客服与管理员都可以执行——若只有管理员能恢复，申诉就在客服手里
            # 断头了（客服看了工单却什么都做不了，卖家永远等不到上架）。
            # 「客服下架 → 客服自己恢复」的闭环风险由审计留痕兜底：
            # 每次 restore 都写审计并通知卖家，谁改的判一查便知。
            self.require(p['status']=='removed','只有已下架的商品可以恢复上架')
            # 最小制衡：客服可以复核恢复他人处置的商品，但不能恢复自己下架的——
            # 「客服下架 → 客服自己恢复」仍然是一个没有第二双眼睛的闭环。
            # 换人复核（其他客服或管理员）后审计里自然留下两段记录。
        else:raise DomainError('不支持的处置动作')
        now=time.time()
        with self.tx() as c:
            actor=c.execute('SELECT role,status FROM users WHERE id=?',(u,)).fetchone()
            self.require(actor and actor['status']=='active' and actor['role'] in ['admin','support','developer'],'当前账号无商品管理权限',403)
            self.require(p['seller_id']!=u or (action=='delist' and actor['role'] in ('admin','developer')),'该操作不能用于自己发布的商品',403)
            if action=='restore':self.require(actor['role'] in ['admin','support','developer'],'只有客服、管理员或开发者可以恢复上架',403)
            if action=='restore' and actor['role']=='support':
                # 最小制衡落地：客服可以复核恢复他人处置的商品，
                # 但不能恢复自己下架的——否则「下架→恢复」没有第二双眼睛。
                self.require(p['delisted_by']!=u,'不能恢复自己下架的商品，请交由其他客服或管理员复核',403)
            current=c.execute('SELECT seller_id,status FROM products WHERE id=?',(pid,)).fetchone()
            self.require(current and current['seller_id']==p['seller_id'] and current['status']==p['status'],'商品状态已变化，请刷新后重试',409)
            if action=='delist':
                # 一并清掉未到期的置顶，否则恢复后会带着旧置顶时间直接跳到最前面。
                c.execute("UPDATE products SET status='removed',delisted_by=?,promoted_until=0 WHERE id=?",(u,pid))
            else:
                c.execute("UPDATE products SET status='available',delisted_by=0 WHERE id=?",(pid,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,p['seller_id'],'product_moderate',reason,now))
            body=(f'你的商品「{p["title"]}」（#{pid}）已被平台下架。理由：{reason}。'
                  f'如有异议，可在客服中心提交申诉。') if action=='delist' else \
                 f'你的商品「{p["title"]}」（#{pid}）已恢复上架。'
            self.notify(c,p['seller_id'],'product_moderate',body)
        return self.product(pid,u)

    def review_product(self,u,pid,decision,reason=None):
        """人工复核被自动审核标记为「平台限制」的商品。

        自动审核（app/moderation）只把命中结果写进 products.data.moderation，
        在此之前**没有任何代码把 reviewed 改回 true**，所以中危商品会永久停在
        「审核中」角标上，message_for() 承诺的「通过后会正常展示」无法兑现。
        这个方法是那个缺口的出口。

        approve —— 撤下标记，商品照常展示；
        reject  —— 驳回归到 moderate_product 走强制下架（含审计、通知、delisted_by）。
        """
        self.staff(u);self.require(decision in ['approve','reject'],'复核结论无效')
        p=self.row('SELECT * FROM products WHERE id=?',(pid,))
        self.require(p,'商品不存在',404)
        self.require(p['seller_id']!=u,'不能复核自己发布的商品',403)
        data=json.loads(p['data']);mark=data.get('moderation')
        self.require(mark and not mark.get('reviewed'),'该商品当前没有待复核的审核标记')
        if decision=='reject':
            return self.moderate_product(u,pid,'delist',self.text(reason,500,'驳回理由'))
        note=str(reason or '').strip()[:500]
        mark.update({'reviewed':True,'reviewed_by':u,'reviewed_at':time.time()})
        if note:mark['review_note']=note
        data['moderation']=mark
        with self.tx() as c:
            c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),pid))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,p['seller_id'],'product_review',note or '复核通过，未记录说明',time.time()))
            self.notify(c,p['seller_id'],'product_review',f'你的商品「{p["title"]}」（#{pid}）已通过人工复核，恢复正常展示。')
        return self.product(pid,u)

    def removed_products(self,u):
        """平台视角的「已下架」列表。

        products() 只出在售，my_products() 只出自己发布的，两处都看不到
        「被平台下架的是哪些、谁下的、还能不能恢复」。没有这个视图，
        强制下架就是个单向操作——下完之后连管理员自己都找不回来。

        附带 relist_locked：退款冻结（delisted_by=0 但卷入退款/争议）的
        商品同样需要平台复核后恢复，工作台要能把这类行也标出来。"""
        self.staff(u)
        result=[]
        for row in self.rows("SELECT id FROM products WHERE status='removed' ORDER BY id DESC LIMIT 200"):
            p=self.product(row['id'],u)
            p['relist_locked'],p['lock_reason']=self._relist_lock(p,p['seller_id'])
            result.append(p)
        return result

    def sellers(self,u):
        """店铺视角：每个卖家还有多少在售、多少已被平台下架。

        反引流实战里最常见的是「这个人整店都在导流」，而商品流是按商品平的，
        运营得先自己看出「这 8 件都是同一个人发的」。这个接口就是那个视图。
        """
        self.staff(u)
        return self.rows(
            """SELECT p.seller_id id,u.nickname,u.score,u.status user_status,
                      SUM(CASE WHEN p.status='available' THEN 1 ELSE 0 END) available,
                      SUM(CASE WHEN p.status='removed' THEN 1 ELSE 0 END) removed,
                      COUNT(*) total
               FROM products p JOIN users u ON u.id=p.seller_id
               GROUP BY p.seller_id
               ORDER BY available DESC, total DESC LIMIT 200""")

    def moderate_seller(self,u,seller_id,reason):
        """批量下架整店：一次把该卖家全部在售商品置为平台处置。

        为什么要有它：单件下架要一件一件点，遇到整店导流时运营会点到放弃，
        或者干脆只下架最显眼的两件——剩下的继续在商品流里挂着。

        为什么是**一个事务一次审计**而不是循环调用 moderate_product：
        循环会产生 N 条审计、N 条通知，卖家打开通知中心看到 8 条一模一样的消息，
        而审计里也看不出「这是一次整店处置」还是「运营点了 8 次」。
        处置是一个动作，就应该只有一条记录。

        权限：仅管理员。单件下架客服就能做，批量属于「一次改变一个店铺的状态」，
        按分权原则（会不会让平台自己成为需要被追责的一方）归管理员。
        """
        self.admin(u)
        seller_id=int(seller_id)
        reason=self.text(reason,500,'处置理由')
        self.require(seller_id!=u,'不能处置自己发布的商品')
        seller=self.row('SELECT id,nickname FROM users WHERE id=?',(seller_id,))
        self.require(seller,'卖家不存在',404)
        rows=self.rows("SELECT id FROM products WHERE seller_id=? AND status='available'",(seller_id,))
        self.require(rows,'该卖家当前没有在售商品可下架')
        now=time.time()
        with self.tx() as c:
            for p in rows:
                # 与单件下架一致：一并清掉未到期的置顶，避免恢复后带着旧置顶时间跳到最前。
                c.execute("UPDATE products SET status='removed',delisted_by=?,promoted_until=0 WHERE id=?",(u,p['id']))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u,seller_id,'seller_moderate',f'整店下架 {len(rows)} 件：{reason}',now))
            self.notify(c,seller_id,'product_moderate',
                        f'你在售的 {len(rows)} 件商品已被平台下架。理由：{reason}。'
                        f'如有异议，可在客服中心提交申诉。')
        return {'id':seller_id,'count':len(rows),'ids':[p['id'] for p in rows]}

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
