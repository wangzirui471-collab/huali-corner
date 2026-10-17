"""客服模块：工单受理与处理、信誉调整、订单评价。"""
import json, time
from ..core.errors import ValidationMixin, DomainError
from .access import case_access, case_participants


class SupportService(ValidationMixin):
    def create_ticket(self,u,d):
        typ=d.get('type','other');self.require(typ in ['refund','report','appeal','reschedule','other'],'工单类型错误')
        subject=self.text(d.get('subject'),80,'问题标题');body=self.text(d.get('body'),3000,'问题说明');oid=d.get('order_id') or None;pid=d.get('product_id') or None
        refund_mode=d.get('refund_mode','refund_only')
        self.require(refund_mode in ['refund_only','return_refund'],'退款方式无效')
        evidence=self.validate_evidence(u,d.get('evidence',[]))
        with self.tx() as c:
            post_id=d.get('post_id') or None
            if post_id:self.require(c.execute('SELECT id FROM posts WHERE id=?',(int(post_id),)).fetchone(),'社区内容不存在',404)
            related=d.get('related_ticket_id') or None
            if related:
                self.require(typ=='appeal','只有申诉可以关联原工单')
                original=c.execute('SELECT * FROM tickets WHERE id=?',(int(related),)).fetchone()
                self.require(original and u in case_participants(self,original),'不能关联他人工单',403)
                self.require(original['status']=='resolved','请先在原工单补充材料，结案后可申请复核',409)
                oid=original['order_id'];pid=original['product_id'];post_id=original['post_id']
            if oid:
                r=c.execute('SELECT * FROM orders WHERE id=?',(int(oid),)).fetchone()
                self.require(r and u in [r['buyer_id'],r['seller_id']],'不能关联他人订单',403)
                if typ=='refund':
                    self.require(u==r['buyer_id'] and r['status'] in ['paid','awaiting_handover','awaiting_receipt','completed','disputed'],'订单当前不能申请退款')
                    self.require(not c.execute("SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected')",(oid,)).fetchone(),'已有待处理退款')
                    if not r['delivered_at']:refund_mode='refund_only'
                    c.execute("UPDATE orders SET status='disputed' WHERE id=?",(oid,))
            else:self.require(typ!='refund','退款必须关联订单')
            if pid:self.product(int(pid))
            tid=c.execute('INSERT INTO tickets(user_id,order_id,product_id,type,subject,body,created) VALUES(?,?,?,?,?,?,?)',(u,oid,pid,typ,subject,body,time.time())).lastrowid
            c.execute('UPDATE tickets SET refund_mode=?,related_ticket_id=?,post_id=? WHERE id=?',(refund_mode,related,post_id,tid))
            sources = self.case_sources({'product_id': pid, 'post_id': post_id})
            sources.pop('captured', None)
            if related:
                sources = self.case_sources(dict(original))
                sources.pop('captured', None)
            c.execute('UPDATE tickets SET source_snapshot=? WHERE id=?', (json.dumps(sources, ensure_ascii=False), tid))
            self.save_evidence(c,tid,u,evidence,False)
            self.notify_ticket(c,tid,f'ticket:{tid}:created','有新的售后／反馈工单',actor=u,queue=True)
        return self.ticket(u,tid)

    def ticket(self,u,tid):
        r=self.row('SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.id=?',(tid,));self.require(r,'工单不存在',404)
        allowed,staff,worker=case_access(self,u,r)
        self.require(allowed or worker,'不能查看他人工单',403)
        r['restricted']=not (allowed or staff)
        if r['restricted']:
            safe={k:r.get(k) for k in ['id','user_id','order_id','product_id','post_id','type','subject','status','assignee','created','nickname']}
            return {**safe,'restricted':True,'body':'','reason':'','messages':[],'evidence':[]}
        r['sources'] = self.case_sources(r)
        r.pop('source_snapshot', None)
        r['messages']=self.rows('SELECT m.*,u.nickname FROM ticket_messages m JOIN users u ON u.id=m.user_id WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY m.id',(tid,int(staff)))
        r['evidence']=[{'id':x['upload_id'],'url':'/media/'+x['upload_id'],'internal':bool(x['internal'])} for x in self.rows('SELECT upload_id,internal FROM ticket_evidence WHERE ticket_id=? AND (?=1 OR internal=0) ORDER BY created_at',(tid,int(staff)))]
        return r

    def tickets(self,u):
        if self.profile(u)['role'] in ['admin','support']:ids=self.rows('SELECT id FROM tickets ORDER BY id DESC')
        else:ids=self.rows('SELECT t.id FROM tickets t LEFT JOIN orders o ON o.id=t.order_id WHERE t.user_id=? OR o.seller_id=? OR o.buyer_id=? ORDER BY t.id DESC',(u,u,u))
        return [self.ticket(u,r['id']) for r in ids]

    def reply_ticket(self,u,tid,d):
        internal=d.get('internal',False)
        self.require(type(internal) is bool,'内部备注状态必须为布尔值')
        if internal:self.staff(u)
        evidence=self.validate_evidence(u,d.get('evidence',[]))
        with self.tx() as c:
            ticket=c.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
            self.require(ticket,'工单不存在',404)
            participant,worker,_=case_access(self,u,ticket)
            self.require(participant or worker,'请先认领工单后回复',403)
            self.require(not internal or worker,'当事人不能使用内部备注',403)
            self.require(ticket['status']!='resolved','工单已结案，请通过关联申诉申请复核',409)
            message_id=c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',(tid,u,self.text(d.get('body') or ('补充图片证据' if evidence else ''),2000,'回复'),int(internal),time.time())).lastrowid
            self.save_evidence(c,tid,u,evidence,internal)
            self.notify_ticket(c,tid,f'ticket:{tid}:reply:{message_id}','工单有新的回复或材料',actor=u,internal=internal)
        return self.ticket(u,tid)

    def check_conflict(self,u,t):
        if t.get('post_id'):
            post=self.row('SELECT user_id FROM posts WHERE id=?',(t['post_id'],))
            self.require(post and post['user_id']!=u,'不能审核自己发布的互助或社区内容',403)
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
            if t['status']=='resolved':
                self.require(d.get('outcome','resolved')==t['outcome'],'工单已结案，请通过关联申诉申请复核',409)
                return {'ok':True}
            outcome=d.get('outcome','resolved');self.require(outcome in ['refund','reject','resolved','review','claim','request_refund'],'处理方式无效')
            if t['type']=='refund' and outcome in ['refund','reject','resolved']:
                self.require(self.profile(u)['role']=='admin','退款审批仅限平台管理员；客服请提交处理建议',403)
            self.require(not t['assignee'] or t['assignee']==u or self.profile(u)['role']=='admin','工单已由其他客服认领，请由管理员转派',409)
            if outcome=='claim':
                c.execute("UPDATE tickets SET assignee=?,status='processing' WHERE id=?",(u,tid))
            elif outcome=='review':c.execute("UPDATE tickets SET assignee=?,status='review',reason=? WHERE id=?",(u,reason,tid))
            elif outcome=='request_refund':
                self.require(t['type']=='refund' and t['order_id'],'只有售后工单可提交退款建议')
                order=c.execute('SELECT total FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                amount=self.cents(d.get('amount',order['total']))
                self.require(0<amount<=order['total'],'退款建议金额无效')
                c.execute("UPDATE tickets SET assignee=?,status='review',reason=?,requested_amount=? WHERE id=?",(u,reason,amount,tid))
            else:
                if t['order_id']:
                    r=c.execute('SELECT * FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                    self.require(u not in [r['buyer_id'],r['seller_id']],'不能审核自己的交易',403)
                    if outcome=='refund':
                        self.require(t['type']=='refund' and r['status']=='disputed','只有争议退款工单可以退款')
                        if not r['delivered_at']:
                            c.execute("UPDATE tickets SET refund_mode='refund_only' WHERE id=?",(tid,))
                        else:self.require(t['refund_mode']!='return_refund' or t['return_received_at'],'请先由卖家确认收到退回实物，再批准退款')
                        amount=self.cents(d.get('amount',r['total']));self.require(0<amount<=r['total'],'退款不能超过订单金额')
                        self.journal(c,r['id'],'refund',amount)
                        settled=c.execute("SELECT amount FROM ledger WHERE order_id=? AND kind='settlement'",(r['id'],)).fetchone()
                        if settled:self.journal(c,r['id'],'settlement_reversal',min(amount,settled['amount']))
                        elif amount<r['total']:self.journal(c,r['id'],'settlement',r['total']-amount)
                        c.execute("UPDATE orders SET status='refunded' WHERE id=?",(r['id'],))
                        # Refunded physical items are NOT automatically offered again.
                        for p in json.loads(r['items']):c.execute("UPDATE products SET status='removed',removal_reason='refund_removed',version=version+1 WHERE id=?",(p['id'],))
                    elif r['status']=='disputed' and t['type']=='refund':
                        prior='completed' if r['completed_at'] else 'awaiting_receipt' if r['handover_at'] else 'awaiting_handover' if r['delivered_at'] else 'paid'
                        c.execute('UPDATE orders SET status=? WHERE id=?',(prior,r['id']))
                c.execute("UPDATE tickets SET status='resolved',assignee=?,outcome=?,reason=? WHERE id=?",(u,outcome,reason,tid))
            c.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',(u,'ticket_'+outcome,reason,tid,time.time()))
            self.notify_ticket(c,tid,f'ticket:{tid}:{outcome}', '工单处理进度已更新',actor=u,internal=outcome in ['review','request_refund'])
        return {'ok':True}

    def credit_action(self,u,target,delta,reason,tid):
        self.staff(u)
        self.require(False,'自由调整分数已停用，请使用规则处罚、申诉冲回或整改恢复接口',410)

    def credit_history(self,u):
        return self.rows("SELECT id,delta,reason,ticket_id,created,rule_key,reversal_of,score_before,score_after FROM audit WHERE target=? AND type IN ('credit','credit_warning','credit_reversal','credit_recovery') ORDER BY id DESC",(u,))

    def review(self,u,oid,rating,body):
        o=self.order(u,oid);self.require(o['status']=='completed' and u in [o['buyer_id'],o['seller_id']],'完成真实有效订单后才能评价')
        self.require(type(rating) is int and 1<=rating<=5,'评分需1至5分')
        with self.tx() as c:
            c.execute('INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?) ON CONFLICT(order_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body',(oid,u,rating,self.text(body,500,'评价'),time.time()))
        return {'ok':True,'simulation':True}
