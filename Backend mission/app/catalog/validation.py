"""Publication and edits share the same strict listing validation."""
import json
class ListingValidation:
    def _listing_account(self,c,user_id):
        account=c.execute('SELECT score,trading_blocked,is_active FROM users WHERE id=?',(user_id,)).fetchone()
        self.require(account and account['is_active'],'账号不可用',403)
        self.require(account['score']>=60,'信誉分低于60，暂不能发布或恢复，可在客服中心申诉',403)
        self.require(not account['trading_blocked'],'当前账号已限制新交易，可申请申诉',403)

    def _validated_listing(self,c,u,d):
        self._listing_account(c,u)
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
        return dict(title=title,category=d['category'],price=price,delivery_fee=fee,delivery=delivery,region=region,data=json.dumps(clean,ensure_ascii=False))
