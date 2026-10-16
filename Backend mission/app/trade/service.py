"""交易模块：合并下单、订单状态流转、付款前修改订单、模拟账务、超时任务。"""
import json, time
from .inventory import release_product
from ..support.access import can_read_order
from ..core.errors import ValidationMixin, DomainError


class TradeService(ValidationMixin):
    def checkout(self,u,d):
        ids=d.get('product_ids');self.require(isinstance(ids,list) and 1<=len(ids)<=20 and len(set(ids))==len(ids),'请选择1至20件不同商品')
        key=self.text(d.get('key'),100,'请求标识');delivery=d.get('delivery');self.require(delivery in ['pickup','delivery'],'交付方式错误')
        try:appointment=float(d.get('appointment',0))
        except (ValueError,TypeError):raise DomainError('交付时间无效')
        self.require(time.time()+60<appointment<time.time()+86400*30,'请选择未来30天内的交付时间')
        address=self.text(d.get('address'),150,'收货公共地点') if delivery=='delivery' else ''
        with self.tx() as c:
            buyer=c.execute('SELECT is_active,trading_blocked FROM users WHERE id=?',(u,)).fetchone()
            self.require(buyer and buyer['is_active'] and not buyer['trading_blocked'],'当前账号已限制新交易或已停用，可申请申诉',403)
            old=c.execute('SELECT id FROM orders WHERE buyer_id=? AND request_key=?',(u,key)).fetchone()
            if old:return self.order(u,old['id'])
            products=[c.execute('SELECT * FROM products WHERE id=?',(i,)).fetchone() for i in ids]
            self.require(all(products),'商品不存在')
            self.require(len({p['seller_id'] for p in products})==1,'只能合并同一卖家的商品')
            seller=products[0]['seller_id'];self.require(seller!=u,'不能购买自己的商品')
            owner=c.execute('SELECT is_active,trading_blocked FROM users WHERE id=?',(seller,)).fetchone()
            self.require(owner and owner['is_active'] and not owner['trading_blocked'],'卖家当前不能进行新交易',403)
            self.require(all(p['status']=='available' for p in products),'部分商品已被预留或售出',409)
            self.require(all(p['delivery'] in [delivery,'both'] for p in products),'商品不支持所选交付方式')
            items=[]
            for p in products:
                price=p['price'];offer=c.execute("SELECT amount FROM offers WHERE product_id=? AND buyer_id=? AND status='accepted' AND product_version=? ORDER BY id DESC LIMIT 1",(p['id'],u,p['version'])).fetchone()
                if offer:price=offer['amount']
                data=json.loads(p['data']);items.append({'id':p['id'],'title':p['title'],'price':price,'region':p['region'],'edition':data.get('edition',''),'notes':data.get('notes',''),'missing':data.get('missing',''),'accessories':data.get('accessories',''),'photo':data['photos'][0]['url'],'category':p['category'],'description':data.get('description',''),'condition':data.get('condition',''),'photos':data.get('photos',[]),'delivery_fee':p['delivery_fee'],'product_version':p['version']})
            subtotal=sum(p['price'] for p in items);fee=max(p['delivery_fee'] for p in products) if delivery=='delivery' else 0
            oid=c.execute('INSERT INTO orders(buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,appointment,status,created,request_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(u,seller,json.dumps(items,ensure_ascii=False),subtotal,fee,subtotal+fee,delivery,address,appointment,'awaiting_payment',time.time(),key)).lastrowid
            for p in products:c.execute("UPDATE products SET status='reserved' WHERE id=?",(p['id'],))
            self.notify(c,[seller],f'order:{oid}:created','有新订单，等待买家模拟付款','order',oid)
        return self.order(u,oid)

    def order(self,u,oid):
        r=self.row('SELECT * FROM orders WHERE id=?',(oid,));self.require(r,'订单不存在',404)
        self.require(can_read_order(self,u,r),'请先认领关联工单，或检查订单访问权限',403)
        r['items']=json.loads(r['items']);r['ledger']=self.rows('SELECT kind,amount,created FROM ledger WHERE order_id=? ORDER BY id',(oid,))
        r['changes']=self.rows('SELECT * FROM order_changes WHERE order_id=? ORDER BY id DESC',(oid,))
        r['notes']=self.rows('SELECT * FROM order_notes WHERE order_id=? ORDER BY id DESC',(oid,))
        r['buyer']=self.profile(r['buyer_id'])['nickname'];r['seller']=self.profile(r['seller_id'])['nickname'];return r

    def orders(self,u):return [self.order(u,r['id']) for r in self.rows('SELECT id FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC',(u,u))]

    def journal(self,c,oid,kind,amount):c.execute('INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',(oid,kind,amount,time.time()))

    def release(self,c,r):
        for p in json.loads(r['items']):release_product(c,p['id'])

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
                self.require(buyer or status=='awaiting_payment','卖家只能在买家付款前取消订单；已付款的请走客服流程退款',403)
                self.require(status in ['awaiting_payment','paid','cancelled'],'已交付或存在争议，请申请售后')
                if status!='cancelled':
                    if status=='paid':self.journal(c,oid,'refund',r['total'])
                    c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(oid,));self.release(c,r)
                    self.notify(c,[r['seller_id'] if buyer else r['buyer_id']],f'order:{oid}:cancelled',('买家' if buyer else '卖家')+'已取消订单','order',oid)
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

    def update_order(self,u,oid,d):
        """付款前修改订单。付款之后改时间要走 order_action 的 reschedule（需对方确认），
        这里只负责「还没付钱」的那段时间 —— 这时候双方都还没投入成本，改起来没有风险。
        买家可改交付方式、收货地点、交付时间，并可从订单里移除商品；
        卖家只能改交付时间，其余由买家决定。
        移除商品会把该商品释放回「在售」，并重算小计、运费与总额。"""
        with self.tx() as c:
            r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            self.require(r,'订单不存在',404)
            self.require(u in [r['buyer_id'],r['seller_id']],'不能处理他人订单',403)
            buyer=u==r['buyer_id']
            self.require(r['status']=='awaiting_payment','订单已付款，如需改时间请用「申请改约」')
            items=json.loads(r['items']);removed=[]
            if 'product_ids' in d:
                self.require(buyer,'仅买家可调整订单中的商品')
                keep=[int(x) for x in d['product_ids']]
                self.require(keep,'订单至少要保留一件商品')
                self.require(set(keep).issubset({i['id'] for i in items}),'包含不属于本订单的商品')
                for i in items:
                    if i['id'] not in keep:
                        release_product(c,i['id'])
                        removed.append(i['title'])
                items=[i for i in items if i['id'] in keep]
            if 'delivery' in d:
                self.require(buyer,'仅买家可更改交付方式')
            delivery=str(d.get('delivery') or r['delivery'])
            self.require(delivery in ['pickup','delivery'],'交付方式需要是自提或送货')
            if delivery!=r['delivery']:
                for i in items:
                    p=c.execute('SELECT delivery FROM products WHERE id=?',(i['id'],)).fetchone()
                    self.require(p and p['delivery'] in [delivery,'both'],f'「{i["title"]}」不支持所选交付方式')
            raw=d.get('address')
            if raw is not None and raw!=(r['address'] or ''):
                self.require(buyer,'仅买家可更改收货地点')
            if delivery=='delivery':
                address=self.text(raw if raw is not None else (r['address'] or ''),150,'收货公共地点')
            else:
                address=''
            try:appointment=float(d.get('appointment') if d.get('appointment') is not None else r['appointment'])
            except (ValueError,TypeError):raise DomainError('交付时间无效')
            now=time.time()
            self.require(now+60<appointment<now+86400*30,'请选择未来30天内的交付时间')
            subtotal=sum(i['price'] for i in items);fee=0
            if delivery=='delivery':
                fees=[i.get('delivery_fee',c.execute('SELECT delivery_fee FROM products WHERE id=?',(i['id'],)).fetchone()['delivery_fee']) for i in items]
                fee=max(fees) if fees else 0
            c.execute('UPDATE orders SET items=?,subtotal=?,delivery_fee=?,total=?,delivery=?,address=?,appointment=? WHERE id=?',
                      (json.dumps(items,ensure_ascii=False),subtotal,fee,subtotal+fee,delivery,address,appointment,oid))
            for title in removed:
                c.execute('INSERT INTO order_notes(order_id,user_id,body,created) VALUES(?,?,?,?)',(oid,u,f'买家移除商品：{title}',now))
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
