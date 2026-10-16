"""Owner-only versioned edits and inventory-aware listing lifecycle."""
import json
from decimal import Decimal

class CatalogEditing:
    def _owned_listing(self, c, user_id, product_id):
        product=c.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
        self.require(product,'商品不存在',404)
        self.require(product['seller_id']==user_id,'只能管理自己发布的商品',403)
        return product

    def _editable_listing(self, product):
        self.require(product['status']=='available' or (product['status']=='removed' and product['removal_reason']=='seller_delist'),
                     '仅在售或主动下架的商品可编辑；交易中或售后移除须先处理原订单',409)

    def product_edit(self,user_id,product_id):
        with self.tx() as c:
            p=self._owned_listing(c,user_id,product_id)
            self._editable_listing(p)
            data=json.loads(p['data'])
            fields={k:str(data.get(k) or '') for k in ['edition','publisher','notes','missing','accessories','bought','condition','author','isbn','course','major','college','description']}
            fields.update({k:p[k] for k in ['title','category','delivery','region']})
            for key in ['price','delivery_fee']:
                fields[key]=format(Decimal(p[key])/100,'.2f')
            fields['original_price']=format(Decimal(data.get('original_price') or 0)/100,'.2f')
            # Fictional seed assets cannot serve as real uploads when publishing an edited listing.
            photos=[] if data.get('simulation') else data.get('photos',[])
            fields['photos']=[x['id'] for x in photos]
            return {'id':p['id'],'version':p['version'],'fields':fields,'photos':photos,'simulation':bool(data.get('simulation'))}

    def edit_product(self,user_id,product_id,version,fields):
        self.require(type(version) is int and version>0,'商品版本无效')
        fields=self._draft_fields(user_id,fields)
        with self.tx() as c:
            p=self._owned_listing(c,user_id,product_id)
            self._editable_listing(p)
            self.require(p['version']==version,'商品已被修改，请读取新版后再保存',409)
            data=self._validated_listing(c,user_id,self._listing_from_draft(fields))
            # Proof is server-owned private metadata, absent from the public edit DTO.
            prior=json.loads(p['data'])
            if prior.get('proof'):
                clean=json.loads(data['data']);clean['proof']=prior['proof']
                data['data']=json.dumps(clean,ensure_ascii=False)
            changed=any(p[k]!=v for k,v in data.items())
            c.execute('UPDATE products SET title=?,category=?,price=?,delivery_fee=?,delivery=?,region=?,data=?,version=version+1 WHERE id=? AND version=?',
                (*data.values(),product_id,version))
            if changed:c.execute("UPDATE offers SET status='expired' WHERE product_id=? AND status IN ('pending','accepted')",(product_id,))
        return self.product(product_id,user_id)

    def _can_restore(self,c,user_id,p):
        self._listing_account(c,user_id)
        self.require(p['status']=='removed' and p['removal_reason']=='seller_delist',
                     '此商品不是主动下架；售后须先确认实物退回与退款，违规或历史状态须客服核对',409)
        self.require(not c.execute("SELECT id FROM products WHERE stock_key=? AND id<>? AND (id>? OR status IN ('available','reserved','sold'))",
                                  (p['stock_key'],p['id'],p['id'])).fetchone(),'同一实物已有更新的出售记录',409)

    def set_product_status(self,user_id,product_id,action):
        with self.tx() as c:
            p=self._owned_listing(c,user_id,product_id)
            if action=='delist':
                self.require(p['status']=='available','只有在售的商品可以下架',409)
                status,reason='removed','seller_delist'
            elif action=='relist':
                self._can_restore(c,user_id,p)
                status,reason='available',''
            else:self.require(False,'不支持的商品操作')
            c.execute('UPDATE products SET status=?,removal_reason=?,version=version+1 WHERE id=?',(status,reason,product_id))
            c.execute("UPDATE offers SET status='expired' WHERE product_id=? AND status IN ('pending','accepted')",(product_id,))
        return self.product(product_id,user_id)
