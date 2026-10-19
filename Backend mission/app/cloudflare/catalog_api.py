"""Atomic D1 adapters for catalog mutations and versioned user profiles."""
import base64
import hashlib
import io
import json
import secrets
import time
from PIL import Image, ImageOps, UnidentifiedImageError
from ..core.errors import ValidationMixin, DomainError
from ..moderation import FREE_TEXT_FIELDS, WORD_ONLY_FIELDS, _rebuild, message_for, report_of
from ..account.profiles import (PROFILE_WRITABLE, DEGREE_LEVELS, STUDY_STATUSES,
                                user_legacy_education, user_legacy_options)
from ..account.avatars import AVATAR_ID, MAX_AVATAR_BYTES
from .http import json_body, json_response, require

ROUTES = {
 '/api/upload':'upload', '/api/publish':'publish', '/api/product/status':'status',
 '/api/product/promote':'promote', '/api/product/moderate':'moderate',
 '/api/product/review':'review', '/api/react':'react', '/api/offer':'offer',
 '/api/offer/accept':'accept', '/api/user/profile':'profile',
 '/api/user/avatar/upload':'avatar_upload', '/api/user/avatar':'avatar', '/api/me':'me',
}
CATALOG_ROUTES={p:((('GET','POST') if p in ('/api/user/profile','/api/me') else ('POST',)),
                   'cf_catalog_'+name) for p,name in ROUTES.items()}

class CatalogApi:
    @staticmethod
    def cf_catalog_id(value):
        require(type(value) is int and value>0, '标识须为正整数')
        return value

    async def cf_catalog_payload(self,request,staff=False):
        uid=await self.page_user(request,staff=staff)
        return uid,await json_body(request)

    async def cf_catalog_product(self,pid,uid):
        # Existing product() includes reaction flags and private moderation rules.
        # Use an explicit projection instead of synthesizing an authenticated request.
        row=await self.db.first('SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?',(pid,))
        require(row,'商品不存在',404)
        item=await self.listing_dto(row)
        mark=json.loads(row['data'] or '{}').get('moderation')
        role=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,))
        if mark and (uid==row['seller_id'] or role in ('admin','support','developer')): item['moderation']=mark
        item['seller_trusted']=(await self.trusted_map([row['seller_id']])).get(row['seller_id'],False)
        item['likes']=await self.db.scalar("SELECT count(*) FROM reactions WHERE product_id=? AND kind='like'",(pid,))
        for key,kind in [('liked','like'),('favorited','favorite')]:
            item[key]=bool(await self.db.first('SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind=?',(pid,uid,kind)))
        return json_response(item)

    async def cf_catalog_guard(self,uid,sql,params,statements,message="状态已变化，请重试"):
        return await self.db.guarded_batch(
          "SELECT 1 WHERE EXISTS(SELECT 1 FROM users WHERE id=? AND status='active') AND EXISTS("+sql+")",
          (uid,)+tuple(params),statements,message=message)

    @staticmethod
    def cf_catalog_decode(value,limit):
        require(isinstance(value,str) and value,'无效图片编码')
        require(len(value)<=4*((limit+2)//3),'图片过大',413)
        try: raw=base64.b64decode(value,validate=True)
        except (ValueError,TypeError): raise DomainError('无效图片编码') from None
        require(0<len(raw)<=limit,'图片过大',413)
        return raw

    async def cf_catalog_save_image(self,uid,raw,avatar=False,angle=None,private=False):
        await self.require_capacity()
        if avatar:
            normalized=self.media_store.normalize(raw)
            fid='ua_'+secrets.token_hex(16)
        else:
            require(angle in ('front','side','top','extra','proof'),'图片角度不正确')
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    require(im.format in ('JPEG','PNG','WEBP'),'请上传有效的JPEG/PNG/WebP图片')
                    require(0<im.width*im.height<=20000000,'图片尺寸过大')
                    im.verify()
                with Image.open(io.BytesIO(raw)) as im:
                    im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((1600,1600))
                    clean=Image.new('RGB',im.size);clean.paste(im)
                    out=io.BytesIO();clean.save(out,'WEBP',quality=85);normalized=out.getvalue()
            except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombError):
                raise DomainError('请上传有效的JPEG/PNG/WebP图片') from None
            fid=secrets.token_hex(16)
        # Unique scope avoids deleting a shared digest object after a DB failure.
        scope=('avatar-' if avatar else 'upload-')+fid
        key=self.media_store.key_for(scope,uid,normalized)
        try:
            written=await self.media_store._bucket.put(key,normalized,{
              'httpMetadata':{'contentType':'image/webp'},'customMetadata':{'owner':str(uid),'scope':scope}})
            require(written is not None,'图片保存失败，请稍后重试',503)
        except BaseException:
            # This random scope has never been registered or returned to a client.
            try: await self.media_store.delete(key)
            except Exception: pass
            raise
        digest=hashlib.sha256(normalized).hexdigest()
        try:
            statement=('INSERT INTO user_avatar_uploads(upload_id,user_id,path,digest,created_at) VALUES(?,?,?,?,?)',
                      (fid,uid,key,digest,time.time())) if avatar else (
                      'INSERT INTO uploads(id,user_id,path,digest,angle,private) VALUES(?,?,?,?,?,?)',
                      (fid,uid,key,digest,angle,int(private)))
            await self.cf_catalog_guard(uid,'SELECT 1',(),[statement])
        except BaseException:
            # Never delete if the DB outcome is uncertain and a row references it.
            try:
                table='user_avatar_uploads' if avatar else 'uploads'; column='upload_id' if avatar else 'id'
                exists=await self.db.first('SELECT 1 FROM '+table+' WHERE '+column+'=?',(fid,))
                if not exists: await self.media_store.delete(key)
            except Exception: pass
            raise
        return json_response({'upload_id':fid,'preview_url':'/media/'+fid} if avatar else
                             {'id':fid,'url':'/media/'+fid,'angle':angle,'private':private})

    async def cf_catalog_upload(self,request):
        uid,d=await self.cf_catalog_payload(request)
        return await self.cf_catalog_save_image(uid,self.cf_catalog_decode(d.get('content'),5*1024*1024),angle=d.get('angle'),private=bool(d.get('private',False)))

    async def cf_catalog_avatar_upload(self,request):
        uid,d=await self.cf_catalog_payload(request)
        require(set(d)=={'content'},'头像参数不合法')
        return await self.cf_catalog_save_image(uid,self.cf_catalog_decode(d['content'],MAX_AVATAR_BYTES),avatar=True)

    async def cf_catalog_publish(self,request):
        uid,d=await self.cf_catalog_payload(request);await self.require_capacity()
        require((await self.profile_dto(uid))['score']>=60,'信誉分低于60，暂不能发布；可在客服中心申诉',403)
        title=ValidationMixin.text(d.get('title'),80,'标题');description=ValidationMixin.text(d.get('description'),3000,'商品介绍')
        require(d.get('category') in ('books','living','sports','electronics'),'请选择二手书、宿舍生活、运动闲置或电子产品')
        price=ValidationMixin.cents(d.get('price'));fee=ValidationMixin.cents(d.get('delivery_fee',0),'送货费')
        delivery=d.get('delivery','pickup');require(delivery in ('pickup','delivery','both'),'请选择交付方式')
        region=ValidationMixin.text(d.get('region'),80,'自提/送货区域')
        ids=d.get('photos');require(isinstance(ids,list) and 3<=len(ids)<=9 and all(isinstance(i,str) for i in ids) and len(set(ids))==len(ids),'需要三张不同角度实拍图，最多九张')
        photos=[await self.db.first('SELECT * FROM uploads WHERE id=?',(i,)) for i in ids]
        require(all(p and p['user_id']==uid and not p['private'] for p in photos),'只能使用本人上传的公开商品图')
        require({'front','side','top'}.issubset({p['angle'] for p in photos}),'请补齐正面、侧面和顶部照片')
        require(len({p['digest'] for p in photos})==len(photos),'重复图片不能凑数')
        if d['category']=='books':
            for k,label in [('edition','版次'),('publisher','出版社'),('notes','笔记情况'),('missing','缺页情况'),('accessories','附件情况')]: ValidationMixin.text(d.get(k),100,label)
        clean={k:d.get(k,'') for k in ['edition','publisher','notes','missing','accessories','bought','condition','author','isbn','course','major','college']}
        clean.update(description=description,photos=[{'id':p['id'],'url':'/media/'+p['id'],'angle':p['angle']} for p in photos],original_price=ValidationMixin.cents(d.get('original_price',0),'原价'),simulation=False)
        proof=d.get('proof')
        if proof:
            require(isinstance(proof,str),'凭证无效')
            pr=await self.db.first('SELECT * FROM uploads WHERE id=?',(proof,));require(pr and pr['user_id']==uid and pr['private'],'凭证无效');clean['proof']=proof
        engine=await self.cf_rules()
        hits=list(engine.scan(' \n '.join(str(d.get(k) or '') for k in FREE_TEXT_FIELDS))['hits'])
        for k in WORD_ONLY_FIELDS:
            if d.get(k): hits.extend(engine.hits(str(d[k]),with_patterns=False))
        report=_rebuild(hits);require(not report['blocked'],'不能发布：'+message_for(report),422)
        marked=report_of(report)
        if marked:clean['moderation']=marked
        pid=secrets.randbits(48)
        guard="SELECT 1 FROM users WHERE id=? AND score>=60"
        params=[uid]
        for p in photos:
            guard+=' AND EXISTS(SELECT 1 FROM uploads WHERE id=? AND user_id=? AND private=0 AND digest=? AND angle=?)';params.extend((p['id'],uid,p['digest'],p['angle']))
        if proof:guard+=' AND EXISTS(SELECT 1 FROM uploads WHERE id=? AND user_id=? AND private=1)';params.extend((proof,uid))
        await self.cf_catalog_guard(uid,guard,params,[('INSERT INTO products(id,seller_id,title,category,price,delivery_fee,delivery,region,data,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,uid,title,d['category'],price,fee,delivery,region,json.dumps(clean,ensure_ascii=False),time.time()))])
        return json_response({'id':pid,'moderation':{'action':report['action'],'message':message_for(report)} if marked else None})

    async def cf_catalog_status(self,request):
        uid,d=await self.cf_catalog_payload(request);pid=self.cf_catalog_id(d.get('id'))
        p=await self.db.first('SELECT * FROM products WHERE id=?',(pid,));require(p,'商品不存在',404);require(p['seller_id']==uid,'只能管理自己发布的商品',403)
        action=d.get('action');require(action in ('delist','relist'),'不支持的商品操作')
        require(p['status']==('available' if action=='delist' else 'removed'),'商品状态不支持此操作')
        guard='SELECT 1 FROM products WHERE id=? AND seller_id=? AND status=?';params=[pid,uid,p['status']]
        if action=='relist':
            require(not p['delisted_by'],'该商品由平台处置下架，需在客服中心申诉后由客服恢复',403)
            require((await self.profile_dto(uid))['score']>=60,'信誉分低于60，暂不能重新上架',403)
            locked=await self.db.first("SELECT 1 FROM orders o,json_each(o.items) i WHERE o.status IN ('refunded','partial_refunded','disputed') AND json_extract(i.value,'$.id')=?",(pid,))
            require(not locked,'该商品曾发生退款或争议，需联系客服复核后才能重新上架',403)
            guard+=" AND coalesce(delisted_by,0)=0 AND EXISTS(SELECT 1 FROM users WHERE id=? AND score>=60) AND NOT EXISTS(SELECT 1 FROM orders o,json_each(o.items) i WHERE o.status IN ('refunded','partial_refunded','disputed') AND json_extract(i.value,'$.id')=?)";params.extend((uid,pid))
        await self.cf_catalog_guard(uid,guard,params,[('UPDATE products SET status=?,promoted_until=? WHERE id=?',('removed' if action=='delist' else 'available',0 if action=='delist' else p['promoted_until'],pid))])
        return await self.cf_catalog_product(pid,uid)

    async def cf_catalog_promote(self,request):
        uid,d=await self.cf_catalog_payload(request);pid=self.cf_catalog_id(d.get('id'))
        tiers={'1d':(1,100),'3d':(3,300),'7d':(7,500)};require(isinstance(d.get('tier'),str) and d['tier'] in tiers,'置顶档位无效')
        p=await self.db.first('SELECT * FROM products WHERE id=?',(pid,));require(p,'商品不存在',404);require(p['seller_id']==uid,'只能置顶自己发布的商品',403);require(p['status']=='available','只有「在售」的商品可以置顶')
        days,price=tiers[d['tier']];until=max(p['promoted_until'] or 0,time.time())+days*86400
        await self.cf_catalog_guard(uid,"SELECT 1 FROM products WHERE id=? AND seller_id=? AND status='available' AND coalesce(promoted_until,0)=?",(pid,uid,p['promoted_until'] or 0),[('UPDATE products SET promoted_until=? WHERE id=?',(until,pid)),('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(uid,uid,'promote',f'商品 #{pid} 置顶 {days} 天（模拟支付 ¥{price/100:.2f}）',time.time()))])
        return json_response(dict(id=pid,tier=d['tier'],days=days,price=price,promoted_until=until,simulation=True))

    async def cf_catalog_moderate(self,request):
        uid,d=await self.cf_catalog_payload(request,True)
        return await self.cf_catalog_moderation(uid,d)

    async def cf_catalog_moderation(self,uid,d,expected_data=None):
        pid=self.cf_catalog_id(d.get('id'));p=await self.db.first('SELECT * FROM products WHERE id=?',(pid,));require(p,'商品不存在',404)
        if expected_data is not None: require(p['data']==expected_data,'商品状态已变化，请刷新后重试',409)
        role=await self.db.scalar('SELECT role FROM users WHERE id=?',(uid,));action=d.get('action')
        require(action in ('delist','restore'),'不支持的处置动作')
        require(p['seller_id']!=uid or (action=='delist' and role in ('admin','developer')),'该操作不能用于自己发布的商品',403)
        require(p['status']==('available' if action=='delist' else 'removed'),'商品状态不支持此操作')
        require(not(action=='restore' and role=='support' and p['delisted_by']==uid),'不能恢复自己下架的商品，请交由其他客服或管理员复核',403)
        reason=ValidationMixin.text(d.get('reason'),500,'处置理由');now=time.time()
        guard="SELECT 1 FROM products p JOIN users a ON a.id=? WHERE p.id=? AND p.seller_id=? AND p.status=? AND p.data=? AND coalesce(p.delisted_by,0)=? AND a.role IN ('admin','support','developer') AND (p.seller_id<>a.id OR (?='delist' AND a.role IN ('admin','developer'))) AND NOT (?='restore' AND a.role='support' AND p.delisted_by=a.id)"
        params=(uid,pid,p['seller_id'],p['status'],p['data'],p['delisted_by'] or 0,action,action)
        body=f'你的商品「{p["title"]}」（#{pid}）'+('已被平台下架。理由：'+reason+'。如有异议，可在客服中心提交申诉。' if action=='delist' else '已恢复上架。')
        await self.cf_catalog_guard(uid,guard,params,[('UPDATE products SET status=?,delisted_by=?,promoted_until=? WHERE id=?',('removed' if action=='delist' else 'available',uid if action=='delist' else 0,0 if action=='delist' else p['promoted_until'],pid)),('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(uid,p['seller_id'],'product_moderate',reason,now)),('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)',(p['seller_id'],'product_moderate',body,now))])
        return await self.cf_catalog_product(pid,uid)

    async def cf_catalog_review(self,request):
        uid,d=await self.cf_catalog_payload(request,True);pid=self.cf_catalog_id(d.get('id'));decision=d.get('decision');require(decision in ('approve','reject'),'复核结论无效')
        p=await self.db.first('SELECT * FROM products WHERE id=?',(pid,));require(p,'商品不存在',404);require(p['seller_id']!=uid,'不能复核自己发布的商品',403)
        data=json.loads(p['data'] or '{}');mark=data.get('moderation');require(mark and not mark.get('reviewed'),'该商品当前没有待复核的审核标记')
        if decision=='reject':return await self.cf_catalog_moderation(uid,{**d,'action':'delist'},expected_data=p['data'])
        note=str(d.get('reason') or '').strip()[:500];now=time.time();mark.update(reviewed=True,reviewed_by=uid,reviewed_at=now)
        if note:mark['review_note']=note
        await self.cf_catalog_guard(uid,"SELECT 1 FROM products WHERE id=? AND data=? AND seller_id<>? AND EXISTS(SELECT 1 FROM users WHERE id=? AND role IN ('admin','support','developer'))",(pid,p['data'],uid,uid),[('UPDATE products SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),pid)),('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(uid,p['seller_id'],'product_review',note or '复核通过，未记录说明',now)),('INSERT INTO notifications(user_id,kind,body,created) VALUES(?,?,?,?)',(p['seller_id'],'product_review',f'你的商品「{p["title"]}」（#{pid}）已通过人工复核，恢复正常展示。',now))])
        return await self.cf_catalog_product(pid,uid)

    async def cf_catalog_react(self,request):
        uid,d=await self.cf_catalog_payload(request);pid=self.cf_catalog_id(d.get('product_id'));kind=d.get('kind');require(kind in ('like','favorite'),'无效操作');require(type(d.get('on')) is bool,'无效操作')
        p=await self.db.first('SELECT status FROM products WHERE id=?',(pid,));require(p,'商品不存在',404);require(p['status']!='removed','商品已下架，无法收藏或点赞')
        stmt=('INSERT OR IGNORE INTO reactions VALUES(?,?,?)',(uid,pid,kind)) if d['on'] else ('DELETE FROM reactions WHERE user_id=? AND product_id=? AND kind=?',(uid,pid,kind))
        await self.cf_catalog_guard(uid,"SELECT 1 FROM products WHERE id=? AND status<>'removed'",(pid,),[stmt])
        return await self.cf_catalog_product(pid,uid)

    async def cf_catalog_offer(self,request):
        uid,d=await self.cf_catalog_payload(request);await self.require_capacity();pid=self.cf_catalog_id(d.get('product_id'));amount=ValidationMixin.cents(d.get('amount'),'出价')
        p=await self.db.first('SELECT * FROM products WHERE id=?',(pid,));require(p,'商品不存在',404);require(p['seller_id']!=uid and p['status']=='available','当前商品不能出价');require(0<amount<p['price'],'出价需低于商品价且不能为0')
        cutoff=time.time()-86400;require(not await self.db.first("SELECT 1 FROM offers WHERE product_id=? AND status='accepted' AND (accepted_at IS NULL OR accepted_at>?)",(pid,cutoff)),'该商品已有报价被接受，正在等待成交')
        oid=secrets.randbits(48)
        await self.cf_catalog_guard(uid,"SELECT 1 FROM products WHERE id=? AND seller_id<>? AND status='available' AND price>? AND NOT EXISTS(SELECT 1 FROM offers WHERE product_id=? AND status='accepted' AND (accepted_at IS NULL OR accepted_at>?))",(pid,uid,amount,pid,cutoff),[('INSERT INTO offers(id,product_id,buyer_id,amount,created) VALUES(?,?,?,?,?)',(oid,pid,uid,amount,time.time()))])
        return json_response({'id':oid})

    async def cf_catalog_accept(self,request):
        uid,d=await self.cf_catalog_payload(request);oid=self.cf_catalog_id(d.get('id'));require(type(d.get('accept')) is bool,'无效操作')
        r=await self.db.first('SELECT o.*,p.seller_id,p.status product_status FROM offers o JOIN products p ON p.id=o.product_id WHERE o.id=?',(oid,));require(r and r['seller_id']==uid,'不能处理他人报价',403);require(r['status']=='pending','该报价已处理')
        accept=d['accept'];statements=[];guard="SELECT 1 FROM offers o JOIN products p ON p.id=o.product_id WHERE o.id=? AND p.seller_id=? AND o.status='pending'";params=[oid,uid]
        if accept:
            require(r['product_status']=='available','商品已下架或售出，不能接受报价')
            guard+=" AND p.status='available' AND NOT EXISTS(SELECT 1 FROM offers a WHERE a.product_id=p.id AND a.status='accepted' AND (a.accepted_at IS NULL OR a.accepted_at>?))";params.append(time.time()-86400)
            statements.append(("UPDATE offers SET status='rejected' WHERE product_id=? AND status='pending' AND id<>?",(r['product_id'],oid)))
        statements.append(('UPDATE offers SET status=?,accepted_at=? WHERE id=?',('accepted' if accept else 'rejected',time.time() if accept else r['accepted_at'],oid)))
        await self.cf_catalog_guard(uid,guard,params,statements);return json_response({'ok':True})

    async def cf_catalog_profile(self,request):
        if request.method=='GET':return await self.user_profile(request)
        uid,d=await self.cf_catalog_payload(request)
        require(not(set(d)-PROFILE_WRITABLE),'包含不可修改的资料字段')
        return await self.cf_catalog_profile_save(uid,d)

    async def cf_catalog_me(self,request):
        if request.method=='GET':return await self.me(request)
        uid,d=await self.cf_catalog_payload(request)
        return await self.cf_catalog_profile_save(uid,d,legacy=True)

    async def cf_catalog_profile_save(self,uid,d,legacy=False):
        current=await self.db.first('SELECT * FROM users WHERE id=?',(uid,));version=d.get('profile_version',current['profile_version'] if legacy else None)
        require(type(version) is int and version>=0,'资料版本须为非负整数');require(current['profile_version']==version,'资料已更新，请重新载入并核对',409)
        values={k:current[k] for k in ('nickname','major','bio','degree_level','study_status','education')}
        for k,maximum,label in [('nickname',24,'昵称'),('major',80,'专业'),('bio',300,'简介')]:
            if k in d or legacy:
                v=d.get(k,'')
                if k=='nickname':values[k]=ValidationMixin.text(v,maximum,label)
                elif legacy:values[k]=str(v)[:maximum]
                else:require(isinstance(v,str) and len(v)<=maximum,f'{label}须为不超过{maximum}字的文字');values[k]=v
        if legacy:
            if 'education' in d and d['education']!=current['education']:
                require(d['education'] in ('本科','专科','已毕业','其他'),'暂不开放该层次');values['education']=d['education'];values['degree_level'],values['study_status']=user_legacy_options(d['education'])
        else:
            for k,allowed in [('degree_level',DEGREE_LEVELS),('study_status',STUDY_STATUSES)]:
                if k in d:require(isinstance(d[k],str) and d[k] in allowed,'学历层次或在读状态选项不合法');values[k]=d[k]
            if any(values[k]!=current[k] for k in ('degree_level','study_status')):values['education']=user_legacy_education(values['degree_level'],values['study_status'])
        await self.cf_catalog_guard(uid,'SELECT 1 FROM users WHERE id=? AND profile_version=?',(uid,version),[('UPDATE users SET nickname=?,major=?,bio=?,degree_level=?,study_status=?,education=?,college=?,profile_version=profile_version+1 WHERE id=?',tuple(values[k] for k in ('nickname','major','bio','degree_level','study_status','education'))+('计算机工程学院',uid))],message='资料已更新，请重新载入并核对')
        return json_response(await self.profile_dto(uid))

    async def cf_catalog_avatar(self,request):
        uid,d=await self.cf_catalog_payload(request);require(set(d)=={'upload_id','profile_version'},'头像参数不合法');fid=d['upload_id'];version=d['profile_version']
        require(type(version) is int and version>=0,'资料版本须为非负整数');require(fid is None or (isinstance(fid,str) and AVATAR_ID.fullmatch(fid)),'头像标识不合法')
        current=await self.profile_dto(uid);require(current['profile_version']==version,'资料已更新，请重新载入并核对',409)
        guard='SELECT 1 FROM users WHERE id=? AND profile_version=?';params=[uid,version]
        if fid:
            record=await self.db.first('SELECT * FROM user_avatar_uploads WHERE upload_id=?',(fid,));require(record,'头像不存在，请重新上传',404);require(record['user_id']==uid,'只能选择本人上传的头像',403)
            await self.media_store.read(record['path'])
            guard+=' AND EXISTS(SELECT 1 FROM user_avatar_uploads WHERE upload_id=? AND user_id=?)';params.extend((fid,uid))
        await self.cf_catalog_guard(uid,guard,params,[('UPDATE users SET avatar_upload_id=?,profile_version=profile_version+1 WHERE id=?',(fid,uid))],message='资料已更新，请重新载入并核对')
        return json_response(await self.profile_dto(uid))
