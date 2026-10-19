"""交易模块：合并下单、订单状态流转、付款前修改订单、模拟账务、超时任务。"""
import json, time
from ..core.errors import ValidationMixin, DomainError


class TradeService(ValidationMixin):
    def checkout(self,u,d):
        ids=d.get('product_ids');self.require(isinstance(ids,list) and 1<=len(ids)<=20 and len(set(ids))==len(ids),'请选择1至20件不同商品')
        key=self.text(d.get('key'),100,'请求标识');delivery=d.get('delivery');self.require(delivery in ['pickup','delivery'],'交付方式错误')
        try:appointment=float(d.get('appointment',0))
        except (ValueError,TypeError):raise DomainError('交付时间无效')
        self.require(time.time()+60<appointment<time.time()+86400*30,'请选择未来30天内的交付时间')
        address=self.text(d.get('address'),150,'收货公共地点') if delivery=='delivery' else ''
        want_id=d.get('want_id')
        with self.tx() as c:
            old=c.execute('SELECT id FROM orders WHERE buyer_id=? AND request_key=?',(u,key)).fetchone()
            if old:return self.order(u,old['id'])
            products=[c.execute('SELECT * FROM products WHERE id=?',(i,)).fetchone() for i in ids]
            self.require(all(products),'商品不存在')
            self.require(len({p['seller_id'] for p in products})==1,'只能合并同一卖家的商品')
            seller=products[0]['seller_id'];self.require(seller!=u,'不能购买自己的商品')
            # 卖家状态校验（F-01）：被封禁 / 注销 / 停用的卖家，商品不再可下单。
            self.require(c.execute("SELECT 1 FROM users WHERE id=? AND status='active'",(seller,)).fetchone(),'卖家当前不可交易',409)
            self.require(all(p['status']=='available' for p in products),'部分商品已被预留或售出',409)
            self.require(all(p['delivery'] in [delivery,'both'] for p in products),'商品不支持所选交付方式')
            want=None
            if want_id is not None:
                self.require(isinstance(want_id,int) or str(want_id).isdigit(),'求购编号无效')
                want=c.execute("SELECT * FROM wants WHERE id=?",(int(want_id),)).fetchone()
                self.require(want and want['status']=='open','该求购已成交或不存在')
            items=[]
            for p in products:
                price=p['price'];offer=c.execute("SELECT amount FROM offers WHERE product_id=? AND buyer_id=? AND status='accepted' ORDER BY id DESC LIMIT 1",(p['id'],u)).fetchone()
                if offer:price=offer['amount']
                data=json.loads(p['data']);items.append({'id':p['id'],'title':p['title'],'price':price,'region':p['region'],'edition':data.get('edition',''),'notes':data.get('notes',''),'missing':data.get('missing',''),'accessories':data.get('accessories',''),'photo':data['photos'][0]['url']})
            subtotal=sum(p['price'] for p in items);fee=max(p['delivery_fee'] for p in products) if delivery=='delivery' else 0
            oid=c.execute('INSERT INTO orders(buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,appointment,status,created,request_key,want_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(u,seller,json.dumps(items,ensure_ascii=False),subtotal,fee,subtotal+fee,delivery,address,appointment,'awaiting_payment',time.time(),key,want['id'] if want is not None else None)).lastrowid
            for p in products:c.execute("UPDATE products SET status='reserved' WHERE id=?",(p['id'],))
            if want is not None:
                # 求购撮合成交：标记该求购已完成，并记 5% 撮合服务费（向下取整到分）。
                # 订单里存 want_id，订单作废时才能靠它把求购放回 open（见 restore_want）。
                c.execute("UPDATE wants SET status='matched' WHERE id=?",(want['id'],))
                self.journal(c,oid,'service_fee',subtotal*5//100)
            self.notify(c,seller,'order_created',f'收到新订单 #{oid}，共 {len(items)} 件商品，等待买家模拟付款。',oid)
        return self.order(u,oid)

    def order(self,u,oid):
        r=self.row('SELECT * FROM orders WHERE id=?',(oid,));self.require(r,'订单不存在',404)
        self.require(u in [r['buyer_id'],r['seller_id']] or self.profile(u)['role'] in ['support','admin'],'不能查看他人订单',403)
        r['items']=json.loads(r['items']);r['ledger']=self.rows('SELECT kind,amount,created FROM ledger WHERE order_id=? ORDER BY id',(oid,))
        r['changes']=self.rows('SELECT * FROM order_changes WHERE order_id=? ORDER BY id DESC',(oid,))
        r['notes']=self.rows('SELECT * FROM order_notes WHERE order_id=? ORDER BY id DESC',(oid,))
        r['buyer']=self.profile(r['buyer_id'])['nickname'];r['seller']=self.profile(r['seller_id'])['nickname'];return r

    def orders(self,u):return [self.order(u,r['id']) for r in self.rows('SELECT id FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC',(u,u))]

    def journal(self,c,oid,kind,amount):c.execute('INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',(oid,kind,amount,time.time()))

    # --- 站内通知 ---------------------------------------------------------
    # 消息页承诺了「订单通知 / 售后通知」，但之前只有聊天消息表，订单事件没有任何出口。
    # 这里用一张独立的 notifications 表承载系统事件，前端在「消息 → 订单通知」里读。
    # post_id 供社区通知（帖子回复 / @提及）跳转；三类 id 互斥，谁有值跳谁。
    def notify(self,c,user_id,kind,body,order_id=None,ticket_id=None,post_id=None):
        c.execute('INSERT INTO notifications(user_id,kind,order_id,ticket_id,post_id,body,created) VALUES(?,?,?,?,?,?,?)',
                  (user_id,kind,order_id,ticket_id,post_id,body,time.time()))

    def notifications(self,u,limit=100):
        rows=self.rows('SELECT id,kind,order_id,ticket_id,post_id,body,read_at,created FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?',(u,int(limit)))
        unread=self.row('SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read_at IS NULL',(u,))['n']
        return {'unread':unread,'items':rows}

    def read_notifications(self,u,nid=None):
        with self.tx() as c:
            if nid:c.execute('UPDATE notifications SET read_at=? WHERE id=? AND user_id=?',(time.time(),int(nid),u))
            else:c.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(time.time(),u))
        return {'ok':True}

    def badges(self,u):
        """顶栏角标的一次性数据源：通知未读 + 聊天未读。

        前端每次路由切换都会拉一次，所以这里必须是两个 COUNT，不能把
        通知列表和会话列表整个捞出来。"""
        return {'notifications':self.notifications(u,1)['unread'],'chat':self.chat_unread(u)}

    # --- 订单作废时的连锁回滚 ---------------------------------------------
    def restore_want(self,c,r):
        """订单作废（取消 / 超时关闭 / 退款）时，把关联的求购放回 open 并冲销撮合服务费。

        没有这一步，求购会永久停在 matched：求购页显示「已成交」、
        「查看匹配」按钮消失（前端只在 open 时渲染），账本上还留着 5% 服务费。
        want_id 为空的老订单直接跳过。"""
        wid=r['want_id']
        if not wid:return
        c.execute("UPDATE wants SET status='open' WHERE id=? AND status='matched'",(wid,))
        fee=c.execute("SELECT amount FROM ledger WHERE order_id=? AND kind='service_fee'",(r['id'],)).fetchone()
        if fee:self.journal(c,r['id'],'service_fee_reversal',fee['amount'])

    def release(self,c,r):
        """订单作废时回收库存。

        卖家状态正常才退回「在售」；卖家已被封禁 / 注销 / 停用时退回
        「已下架」并清掉置顶，不重新进入公开列表（F-01：封禁后待付款
        订单被取消，release() 曾无条件把商品设回 available，商品又暴露
        给其他买家下单）。语义与 Cloudflare 侧 cf_trade_release 一致。
        返回真正恢复在售的商品 id，调用方据此写通知文案。"""
        restored=[]
        for p in json.loads(r['items']):
            pid=p['id']
            # 事务内必须用事务连接 c 查：self.row() 另开连接，读不到本事务未提交数据。
            active=c.execute("SELECT 1 FROM users WHERE id=(SELECT seller_id FROM products WHERE id=?) AND status='active'",(pid,)).fetchone()
            if active:
                c.execute("UPDATE products SET status='available' WHERE id=? AND status='reserved'",(pid,));restored.append(pid)
            else:
                c.execute("UPDATE products SET status='removed',promoted_until=0 WHERE id=? AND status='reserved'",(pid,))
        return restored

    @staticmethod
    def stock_note(restored,total):
        """通知文案：全部商品回到在售才说「释放回在售」，否则说明随卖家处置下架。"""
        return '商品已释放回在售。' if len(restored)==total else '商品已随卖家账号处置下架，暂停公开展示。'

    def complete(self,c,r,now):
        c.execute("UPDATE orders SET status='completed',completed_at=? WHERE id=?",(now,r['id']))
        self.journal(c,r['id'],'settlement',r['total'])
        for p in json.loads(r['items']):c.execute("UPDATE products SET status='sold',promoted_until=0 WHERE id=?",(p['id'],))
        self.notify(c,r['seller_id'],'order_completed',f'订单 #{r["id"]} 买家已确认收货，模拟结算完成。',r['id'])

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
                    self.notify(c,r['seller_id'],'order_paid',f'订单 #{oid} 买家已完成模拟付款，请在 24 小时内确认交付安排。',oid)
                else:self.require(status in ['paid','awaiting_handover','awaiting_receipt','completed'],'当前不可支付')
            elif action=='cancel':
                self.require(buyer or status=='awaiting_payment','卖家只能在买家付款前取消订单；已付款的请走客服流程退款',403)
                self.require(status in ['awaiting_payment','paid','cancelled'],'已交付或存在争议，请申请售后')
                if status!='cancelled':
                    if status=='paid':self.journal(c,oid,'refund',r['total'])
                    c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(oid,))
                    restored=self.release(c,r);self.restore_want(c,r)
                    who='买家' if buyer else '卖家'
                    self.notify(c,r['seller_id'] if buyer else r['buyer_id'],'order_cancelled',f'订单 #{oid} 已被{who}取消，{self.stock_note(restored,len(json.loads(r["items"])))}',oid)
            elif action=='deliver':
                self.require(not buyer and status=='paid','仅卖家可在付款后标记交付')
                c.execute("UPDATE orders SET status='awaiting_handover',schedule_confirmed=1,delivered_at=? WHERE id=?",(now,oid))
                self.notify(c,r['buyer_id'],'order_delivered',f'订单 #{oid} 卖家已标记交付，请核对实物后确认交接。',oid)
            elif action=='handover':
                self.require(buyer and status=='awaiting_handover','请在实际交接后确认')
                c.execute("UPDATE orders SET status='awaiting_receipt',handover_at=? WHERE id=?",(now,oid))
                self.notify(c,r['seller_id'],'order_handover',f'订单 #{oid} 买家已确认交接，24 小时后自动完成收货。',oid)
            elif action=='receive':
                self.require(buyer and status in ['awaiting_receipt','completed'],'请先核对交接再确认收货')
                if status!='completed':self.complete(c,r,now)
            elif action=='confirm_schedule':
                self.require(not buyer and status=='paid','仅卖家可在付款后确认时间')
                c.execute('UPDATE orders SET schedule_confirmed=1 WHERE id=?',(oid,))
            elif action=='reschedule':
                self.require(status in ['paid','awaiting_handover'],'当前不能申请改约')
                appointment=d.get('appointment');self.require(type(appointment) in [int,float] and now+60<appointment<now+86400*30,'请选择未来30天内的改约时间')
                address=self.text(d.get('address') or r['address'] or json.loads(r['items'])[0]['region'],150,'改约地点')
                self.require(not c.execute("SELECT 1 FROM order_changes WHERE order_id=? AND status='pending'",(oid,)).fetchone(),'已有待对方确认的改约')
                c.execute('INSERT INTO order_changes(order_id,proposer,appointment,address,created) VALUES(?,?,?,?,?)',(oid,u,appointment,address,now))
                who='买家' if buyer else '卖家'
                self.notify(c,r['seller_id'] if buyer else r['buyer_id'],'order_reschedule',f'订单 #{oid} {who}申请改约，等待你确认。',oid)
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
                        # 与 release() 同一套卖家状态规则：卖家异常时商品不回到公开在售（F-01）。
                        active=c.execute("SELECT 1 FROM users WHERE id=(SELECT seller_id FROM products WHERE id=?) AND status='active'",(i['id'],)).fetchone()
                        if active:
                            c.execute("UPDATE products SET status='available' WHERE id=? AND status='reserved'",(i['id'],))
                        else:
                            c.execute("UPDATE products SET status='removed',promoted_until=0 WHERE id=? AND status='reserved'",(i['id'],))
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
                fees=[c.execute('SELECT delivery_fee FROM products WHERE id=?',(i['id'],)).fetchone()['delivery_fee'] for i in items]
                fee=max(fees) if fees else 0
            c.execute('UPDATE orders SET items=?,subtotal=?,delivery_fee=?,total=?,delivery=?,address=?,appointment=? WHERE id=?',
                      (json.dumps(items,ensure_ascii=False),subtotal,fee,subtotal+fee,delivery,address,appointment,oid))
            for title in removed:
                c.execute('INSERT INTO order_notes(order_id,user_id,body,created) VALUES(?,?,?,?)',(oid,u,f'买家移除商品：{title}',now))
            # 改单会改小计，撮合服务费必须跟着重算，否则会按改单前的金额一直挂在账本上。
            if r['want_id']:
                row=c.execute("SELECT amount FROM ledger WHERE order_id=? AND kind='service_fee'",(oid,)).fetchone()
                newfee=subtotal*5//100
                if row and row['amount']!=newfee:c.execute('UPDATE ledger SET amount=? WHERE order_id=? AND kind=?',(newfee,oid,'service_fee'))
            if buyer:
                self.notify(c,r['seller_id'],'order_updated',f'订单 #{oid} 买家修改了商品或交付信息，请重新核对。',oid)
        return self.order(u,oid)

    def respond_change(self,u,change_id,accept):
        with self.tx() as c:
            change=c.execute('SELECT * FROM order_changes WHERE id=?',(change_id,)).fetchone();self.require(change,'改约不存在',404)
            o=c.execute('SELECT * FROM orders WHERE id=?',(change['order_id'],)).fetchone()
            self.require(u in [o['buyer_id'],o['seller_id']] and u!=change['proposer'],'仅交易另一方可确认改约',403)
            self.require(o['status'] in ['paid','awaiting_handover'] and change['status']=='pending','改约已失效')
            self.require(change['appointment']>time.time()+60 or not accept,'该时段已过期')
            if accept:c.execute('UPDATE orders SET appointment=?,address=?,schedule_confirmed=1 WHERE id=?',(change['appointment'],change['address'],o['id']))
            c.execute('UPDATE order_changes SET status=? WHERE id=?',('accepted' if accept else 'rejected',change_id))
            self.notify(c,change['proposer'],'order_change_result',f'订单 #{o["id"]} 的改约申请已被{"接受" if accept else "拒绝"}。',o['id'])
        return {'ok':True}

    def tick(self,now=None):
        now=now or time.time()
        with self.tx() as c:
            for r in c.execute("SELECT * FROM orders WHERE status='awaiting_payment' AND created<?",(now-1800,)).fetchall():
                c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],))
                restored=self.release(c,r);self.restore_want(c,r)
                self.notify(c,r['buyer_id'],'order_timeout',f'订单 #{r["id"]} 超过 30 分钟未付款，已自动关闭，{self.stock_note(restored,len(json.loads(r["items"])))}',r['id'])
                self.notify(c,r['seller_id'],'order_timeout',f'订单 #{r["id"]} 超过 30 分钟未付款，已自动关闭。',r['id'])
            # 计时从「付款时间」起算：原先用 created 计时，买家把付款拖到接近 30 分钟上限时，
            # 卖家几乎没有确认窗口就会被自动退款（付款 60 秒后订单变 cancelled）。
            for r in c.execute("SELECT * FROM orders WHERE status='paid' AND schedule_confirmed=0 AND COALESCE(paid_at,created)<?",(now-86400,)).fetchall():
                self.journal(c,r['id'],'refund',r['total'])
                c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],))
                restored=self.release(c,r);self.restore_want(c,r)
                self.notify(c,r['buyer_id'],'order_timeout',f'订单 #{r["id"]} 卖家 24 小时未确认交付安排，已自动取消并模拟退款，{self.stock_note(restored,len(json.loads(r["items"])))}',r['id'])
                self.notify(c,r['seller_id'],'order_timeout',f'订单 #{r["id"]} 超过 24 小时未确认交付安排，已自动取消并退款给买家。',r['id'])
            for r in c.execute("SELECT * FROM orders WHERE status='awaiting_receipt' AND handover_at<?",(now-86400,)).fetchall():
                if not c.execute("SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected')",(r['id'],)).fetchone():
                    self.complete(c,r,now)
                    c.execute('INSERT INTO order_notes(order_id,user_id,body,created) VALUES(?,?,?,?)',(r['id'],0,'超过24小时未确认收货，系统已自动完成收货并结算',now))
            # 清理过期会话与验证码：这几张表原先只靠下次登录覆盖，长期运行会持续堆积。
            c.execute('DELETE FROM sessions WHERE expires<?',(now,))
            c.execute('DELETE FROM otp WHERE expires<?',(now-86400,))
            c.execute('DELETE FROM auth_attempts WHERE reset_at<?',(now-86400,))
            # 被接受的报价 24 小时未成交即作废，商品重新可报价（否则商品被一个
            # 永远不会结算的报价永久占住，其他人想买也买不了）。
            c.execute("UPDATE offers SET status='rejected' WHERE status='accepted' AND accepted_at<?",(now-86400,))
