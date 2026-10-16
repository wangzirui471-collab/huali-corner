"""客服模块：工单受理与处理、信誉调整、订单评价。"""
import json, time
from ..core.errors import ValidationMixin, DomainError


class SupportService(ValidationMixin):
    def create_ticket(self,u,d):
        typ=d.get('type','other');self.require(typ in ['refund','report','appeal','reschedule','other'],'工单类型错误')
        subject=self.text(d.get('subject'),80,'问题标题');body=self.text(d.get('body'),3000,'问题说明');oid=d.get('order_id') or None;pid=d.get('product_id') or None
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
        return self.ticket(u,tid)

    def ticket(self,u,tid):
        r=self.row('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?',(tid,));self.require(r,'工单不存在',404)
        staff=self.profile(u)['role'] in ['support','admin'];allowed=r['user_id']==u
        if r['order_id']:
            o=self.row('SELECT buyer_id,seller_id FROM orders WHERE id=?',(r['order_id'],));allowed=allowed or u in [o['buyer_id'],o['seller_id']]
        self.require(allowed or staff,'不能查看他人工单',403)
        r['messages']=self.rows('SELECT m.*,u.nickname FROM ticket_messages m JOIN users u ON u.id=m.user_id WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY m.id',(tid,int(staff)))
        return r

    def tickets(self,u):
        if self.profile(u)['role'] in ['admin','support']:ids=self.rows('SELECT id FROM tickets ORDER BY id DESC')
        else:ids=self.rows('SELECT t.id FROM tickets t LEFT JOIN orders o ON o.id=t.order_id WHERE t.user_id=? OR o.seller_id=? OR o.buyer_id=? ORDER BY t.id DESC',(u,u,u))
        return [self.ticket(u,r['id']) for r in ids]

    def reply_ticket(self,u,tid,d):
        self.ticket(u,tid);internal=bool(d.get('internal',False))
        if internal:self.staff(u)
        with self.tx() as c:c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',(tid,u,self.text(d.get('body'),2000,'回复'),int(internal),time.time()))
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
            outcome=d.get('outcome','resolved');self.require(outcome in ['refund','reject','resolved','review','claim'],'处理方式无效')
            if outcome=='claim':c.execute("UPDATE tickets SET assignee=?,status='processing' WHERE id=?",(u,tid))
            elif outcome=='review':c.execute("UPDATE tickets SET assignee=?,status='review',reason=? WHERE id=?",(u,reason,tid))
            else:
                if t['order_id']:
                    r=c.execute('SELECT * FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                    self.require(u not in [r['buyer_id'],r['seller_id']],'不能审核自己的交易',403)
                    if outcome=='refund':
                        self.require(t['type']=='refund' and r['status']=='disputed','只有争议退款工单可以退款')
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
        return {'ok':True}

    def credit_action(self,u,target,delta,reason,tid):
        self.staff(u);self.require(self.profile(u)['role']=='admin','仅平台管理员可处理信誉',403)
        self.require(u!=target,'不能处理自己的信誉');self.text(reason,1000,'处罚/复核理由');t=self.ticket(u,tid)
        self.require(type(delta) is int and -100<=delta<=100 and delta!=0,'分值变动无效')
        self.require(t['status']=='resolved','请先核实工单并记录处理结论')
        self.check_conflict(u,t)
        related=set()
        if t['product_id']:related.add(self.product(t['product_id'])['seller_id'])
        if t['order_id']:
            order=self.order(u,t['order_id']);related.update([order['buyer_id'],order['seller_id']])
            self.require(u not in related,'不能处理自己交易的信誉')
        if t['type']=='appeal' and delta>0:related.add(t['user_id'])
        self.require(target in related,'工单与该用户无处罚或复核关联')
        with self.tx() as c:
            self.require(c.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone(),'用户不存在')
            self.require(not c.execute("SELECT 1 FROM audit WHERE target=? AND ticket_id=? AND type='credit'",(target,tid)).fetchone(),'该工单已处理过此用户信誉，请另行复核')
            c.execute('UPDATE users SET score=MAX(0,MIN(100,score+?)) WHERE id=?',(delta,target))
            c.execute('INSERT INTO audit(actor,target,type,delta,reason,ticket_id,created) VALUES(?,?,?,?,?,?,?)',(u,target,'credit',delta,reason,tid,time.time()))
        return self.profile(target)

    def ban_user(self,u,target,banned,reason):
        """封禁 / 解封账号：比扣信誉分更硬的约束。封禁后账号立即下线、
        在售商品下架、无法登录或发起任何操作（鉴权层会拦）。
        仅平台管理员可操作，且不能封禁管理员或自己。"""
        self.staff(u);self.require(self.profile(u)['role']=='admin','仅平台管理员可封禁账号',403)
        self.require(u!=target,'不能封禁自己')
        self.text(reason,500,'封禁/解封理由')
        with self.tx() as c:
            self.require(c.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone(),'用户不存在',404)
            self.require(c.execute('SELECT role FROM users WHERE id=?',(target,)).fetchone()['role']!='admin','不能封禁管理员',403)
            c.execute("UPDATE users SET status=? WHERE id=?",('banned' if banned else 'active',target))
            if banned:
                c.execute('DELETE FROM sessions WHERE user_id=?',(target,))
                c.execute("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'",(target,))
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,target,'ban' if banned else 'unban',reason,time.time()))
        return self.profile(target)

    def credit_history(self,u):
        return self.rows("SELECT delta,reason,ticket_id,created FROM audit WHERE target=? AND type='credit' ORDER BY id DESC",(u,))
    def review(self,u,oid,rating,body):
        o=self.order(u,oid);self.require(o['status']=='completed' and u in [o['buyer_id'],o['seller_id']],'完成真实有效订单后才能评价')
        self.require(type(rating) is int and 1<=rating<=5,'评分需1至5分')
        with self.tx() as c:
            c.execute('INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?) ON CONFLICT(order_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body',(oid,u,rating,self.text(body,500,'评价'),time.time()))
        return {'ok':True,'simulation':True}
