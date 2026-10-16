"""商品模块：发布、三图校验、浏览筛选、收藏点赞、出价、下架与重新上架。"""
import hashlib, io, json, secrets, time
from contextlib import nullcontext
from PIL import Image, ImageOps, UnidentifiedImageError
from ..core.errors import ValidationMixin, DomainError


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

    def publish(self,u,d,*,connection=None,stock_key=None,source_draft_id=None):
        with (self.tx() if connection is None else nullcontext(connection)) as c:
            data=self._validated_listing(c,u,d)
            pid=c.execute('INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created,stock_key,source_draft_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (u,data['title'],data['category'],data['price'],data['delivery_fee'],data['delivery'],data['region'],data['data'],time.time(),stock_key or secrets.token_hex(16),source_draft_id)).lastrowid
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

    def my_products(self,u,status=None):
        """卖家自己的商品列表，含已下架。products() 会把 removed 过滤掉，
        而卖家需要在「我发布的」里看到自己下架掉的东西，所以单独走这里。"""
        result=[]
        for row in self.rows('SELECT id FROM products WHERE seller_id=? ORDER BY id DESC',(u,)):
            p=self.product(row['id'],u)
            if status and p['status']!=status:continue
            result.append(p)
        return result

    def react(self,u,p,kind,on):
        self.product(p);self.require(kind in ['like','favorite'],'无效操作')
        with self.tx() as c:
            if on:c.execute('INSERT OR IGNORE INTO reactions VALUES(?,?,?)',(u,p,kind))
            else:c.execute('DELETE FROM reactions WHERE user_id=? AND product_id=? AND kind=?',(u,p,kind))
        return self.product(p,u)

    def offer(self,u,p,amount):
        self.cents(amount)
        with self.tx() as c:
            item=c.execute('SELECT * FROM products WHERE id=?',(p,)).fetchone()
            self.require(item and item['seller_id']!=u and item['status']=='available','当前商品不能出价')
            oid=c.execute('INSERT INTO offers(product_id,buyer_id,amount,created,product_version) VALUES(?,?,?,?,?)',(p,u,amount,time.time(),item['version'])).lastrowid
        return {'id':oid}

    def offers(self,u):
        return self.rows('SELECT o.*,p.title,p.seller_id,u.nickname FROM offers o JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id WHERE o.buyer_id=? OR p.seller_id=? ORDER BY o.id DESC',(u,u))

    def accept_offer(self,u,oid,accept):
        with self.tx() as c:
            r=c.execute('SELECT o.*,p.seller_id,p.version,p.status AS product_status FROM offers o JOIN products p ON p.id=o.product_id WHERE o.id=?',(oid,)).fetchone()
            self.require(r and r['seller_id']==u,'不能处理他人报价',403)
            self.require(r['status'] in ['pending','accepted','rejected'] and r['product_status']=='available' and r['product_version']==r['version'],'报价已失效，请重新出价',409)
            c.execute('UPDATE offers SET status=? WHERE id=?',('accepted' if accept else 'rejected',oid))
        return {'ok':True}
