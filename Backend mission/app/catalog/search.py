"""Parameterized catalog search with query-bound stable keyset cursors."""
import base64
import hashlib
import json

TEXT_FILTERS=('college','major','course','edition','condition')
FILTERS={'q','category','delivery','min_price','max_price','sort','cursor','page_size','seller','favorite','free',*TEXT_FILTERS}

class CatalogSearch:
    def search_products(self,user_id=None,filters=None):
        f=dict(filters or {})
        self.require(not (f.keys()-FILTERS),'筛选字段无效')
        def number(value,label,default=None):
            if value in (None,''):return default
            self.require(type(value) is int or (isinstance(value,str) and value.isascii() and value.isdigit()),label+'须为非负整数')
            value=int(value);self.require(0<=value<=10000000,label+'超出范围');return value
        size=number(f.get('page_size'),'分页大小',20)
        self.require(size>0,'分页大小须大于0');size=min(size,50)
        minimum=number(f.get('min_price'),'最低价格');maximum=number(f.get('max_price'),'最高价格')
        self.require(minimum is None or maximum is None or minimum<=maximum,'最低价不能高于最高价')
        delivery=f.get('delivery') or ''
        self.require(delivery in ('','pickup','delivery'),'交付方式无效')
        category=f.get('category') or ''
        self.require(category in ('','books','living','sports','electronics'),'商品类别无效')
        sort=f.get('sort') or 'newest'
        self.require(sort in ('newest','price','price_asc','price_desc'),'排序方式无效')
        normalized={k:v for k,v in f.items() if k not in ('cursor','page_size') and v not in (None,'')}
        fingerprint=hashlib.sha256(json.dumps(normalized,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        price="(p.price+CASE WHEN p.delivery='delivery' OR ?='delivery' THEN p.delivery_fee ELSE 0 END)"
        # price parameter is first in SELECT, repeated in bounded range/cursor conditions.
        params=[delivery];where=["p.status='available'"];args=[]
        if f.get('free') in ('1',1):where.append('p.price=0')
        if category:where.append('p.category=?');args.append(category)
        if delivery:where.append("p.delivery IN (?,'both')");args.append(delivery)
        q=f.get('q') or ''
        self.require(isinstance(q,str) and len(q)<=100,'关键词最多100字')
        if q:
            where.append("instr(lower(p.title||' '||COALESCE(json_extract(p.data,'$.description'),'')||' '||COALESCE(json_extract(p.data,'$.isbn'),'')||' '||COALESCE(json_extract(p.data,'$.publisher'),'')||' '||COALESCE(json_extract(p.data,'$.major'),'')||' '||COALESCE(json_extract(p.data,'$.edition'),'')),lower(?))>0")
            args.append(q)
        for key in TEXT_FILTERS:
            value=f.get(key)
            if not value:continue
            self.require(isinstance(value,str) and len(value)<=100,'筛选文字无效')
            expression="COALESCE(json_extract(p.data,'$."+key+"'),'')"
            if value=='unknown':
                where.append('('+expression+"='' OR "+expression+" LIKE '%待%' OR "+expression+" LIKE '%未知%' OR "+expression+" LIKE '%未核对%')")
            else:where.append(expression+'=?');args.append(value)
        if f.get('seller'):
            where.append('p.seller_id=?');args.append(number(f['seller'],'卖家编号'))
        if f.get('favorite'):
            self.require(user_id is not None,'请先登录',401)
            where.append("EXISTS(SELECT 1 FROM reactions r WHERE r.product_id=p.id AND r.user_id=? AND r.kind='favorite')");args.append(user_id)
        for op,value in [('>=',minimum),('<=',maximum)]:
            if value is not None:where.append(price+op+'?');args.extend([delivery,value])
        cursor=f.get('cursor')
        if cursor:
            self.require(isinstance(cursor,str) and len(cursor)<2048,'翻页游标无效')
            try:
                data=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                valid=(isinstance(data,dict) and data.get('query')==fingerprint and all(type(data.get(k)) is int and data[k]>=0 for k in ['max_id','id','price']))
            except (ValueError,TypeError,UnicodeDecodeError):valid=False
            self.require(valid,'筛选条件已变化或游标无效，请重新搜索')
            max_id=data['max_id']
            if sort=='newest':where.append('p.id<?');args.append(data['id'])
            else:
                op='<' if sort=='price_desc' else '>'
                where.append('('+price+op+'? OR ('+price+'=? AND p.id<?))')
                args.extend([delivery,data['price'],delivery,data['price'],data['id']])
        else:max_id=self.row('SELECT COALESCE(MAX(id),0) id FROM products')['id']
        where.append('p.id<=?');args.append(max_id)
        order='p.id DESC' if sort=='newest' else 'effective_price '+('DESC' if sort=='price_desc' else 'ASC')+',p.id DESC'
        rows=self.rows('SELECT p.id,'+price+' AS effective_price FROM products p WHERE '+' AND '.join(where)+' ORDER BY '+order+' LIMIT ?',params+args+[size+1])
        items=[{**self.product(row['id'],user_id),'effective_price':row['effective_price']} for row in rows[:size]]
        has_more=len(rows)>size;next_cursor=None
        if has_more:
            last=rows[size-1]
            data={'query':fingerprint,'max_id':max_id,'id':last['id'],'price':last['effective_price']}
            next_cursor=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
        return {'items':items,'next_cursor':next_cursor,'has_more':has_more}
