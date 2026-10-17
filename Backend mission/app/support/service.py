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
            if oid and typ=='refund':
                self.notify(c,r['seller_id'],'ticket_refund', f'订单 #{oid} 买家已申请售后并暂停结算，请到客服中心查看进展。',oid,tid)
            elif oid:
                other=r['seller_id'] if u==r['buyer_id'] else r['buyer_id']
                self.notify(c,other,'ticket_filed',f'订单 #{oid} 的对方提交了工单 #{tid}（{subject}）。',oid,tid)
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
        if self.profile(u)['role'] in ['admin','support','developer']:ids=self.rows('SELECT id FROM tickets ORDER BY id DESC')
        else:ids=self.rows('SELECT t.id FROM tickets t LEFT JOIN orders o ON o.id=t.order_id WHERE t.user_id=? OR o.seller_id=? OR o.buyer_id=? ORDER BY t.id DESC',(u,u,u))
        return [self.ticket(u,r['id']) for r in ids]

    def reply_ticket(self,u,tid,d):
        self.ticket(u,tid);internal=bool(d.get('internal',False))
        if internal:self.staff(u)
        with self.tx() as c:
            c.execute('INSERT INTO ticket_messages(ticket_id,user_id,body,internal,created) VALUES(?,?,?,?,?)',(tid,u,self.text(d.get('body'),2000,'回复'),int(internal),time.time()))
            # 客服/管理员的公开回复要能通知到相关用户；用户自己的补充留给工作台队列。
            if not internal and self.profile(u)['role'] in ['support','admin','developer']:
                t=c.execute('SELECT user_id,order_id FROM tickets WHERE id=?',(tid,)).fetchone()
                targets={t['user_id']}
                if t['order_id']:
                    o=c.execute('SELECT buyer_id,seller_id FROM orders WHERE id=?',(t['order_id'],)).fetchone()
                    if o:targets.update([o['buyer_id'],o['seller_id']])
                for target in targets-{u}:
                    self.notify(c,target,'ticket_reply',f'工单 #{tid} 客服已回复，请到客服中心查看。',t['order_id'],tid)
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
                        # 但求购撮合必须回滚，否则那条求购会永远停在「已成交」。
                        self.restore_want(c,r)
                        self.notify(c,r['buyer_id'],'refund_done',f'订单 #{r["id"]} 的退款工单已处理，模拟退款 ¥{amount/100:.2f}。',r['id'])
                        self.notify(c,r['seller_id'],'refund_done',f'订单 #{r["id"]} 已按工单结论处理并模拟退款 ¥{amount/100:.2f}。',r['id'])
                        for p in json.loads(r['items']):c.execute("UPDATE products SET status='removed' WHERE id=?",(p['id'],))
                    elif r['status']=='disputed' and t['type']=='refund':
                        prior='completed' if r['completed_at'] else 'awaiting_receipt' if r['handover_at'] else 'awaiting_handover' if r['delivered_at'] else 'paid'
                        c.execute('UPDATE orders SET status=? WHERE id=?',(prior,r['id']))
                c.execute("UPDATE tickets SET status='resolved',assignee=?,outcome=?,reason=? WHERE id=?",(u,outcome,reason,tid))
            c.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',(u,'ticket_'+outcome,reason,tid,time.time()))
            if outcome not in ('claim','review'):
                self.notify(c,t['user_id'],'ticket_resolved',f'工单 #{tid} 已处理完成（{"退款" if outcome=="refund" else "结案" if outcome=="resolved" else "驳回"}），可到客服中心查看处理依据并申请复核。',t['order_id'],tid)
        return {'ok':True}

    def credit_action(self,u,target,delta,reason,tid):
        self.staff(u);self.require(self.is_admin(u),'仅平台管理员或开发者可处理信誉',403)
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
            self.notify(c,target,'credit',f'你的信誉分有变动（{delta:+d} 分），可到客服中心查看处理依据并申诉。',None,tid)
        return self.profile(target)

    def ban_user(self,u,target,banned,reason):
        """封禁 / 解封账号：比扣信誉分更硬的约束。封禁后账号立即下线、
        在售商品下架、无法登录或发起任何操作（鉴权层会拦）。
        仅平台管理员可操作，且不能封禁管理员或自己。

        封禁还必须处理在途订单：卖家被封后不可能再登录推进交付，
        原实现只下架商品，订单会永远卡在 paid / awaiting_handover，
        买家只能自己慢慢摸索售后入口。"""
        self.staff(u);self.require(self.is_admin(u),'仅平台管理员或开发者可封禁账号',403)
        self.require(u!=target,'不能封禁自己')
        self.text(reason,500,'封禁/解封理由')
        with self.tx() as c:
            user=c.execute('SELECT role,status FROM users WHERE id=?',(target,)).fetchone()
            self.require(user,'用户不存在',404)
            self.require(user['role'] not in ('admin','developer'),'不能封禁管理员或开发者',403)
            now=time.time()
            if not banned:
                # 解封只针对「被封禁」的账号；注销过的账号不应被顺手复活。
                self.require(user['status']=='banned','该账号当前不是封禁状态，无法解封')
                c.execute("UPDATE users SET status='active' WHERE id=?",(target,))
            else:
                c.execute("UPDATE users SET status='banned' WHERE id=?",(target,))
                c.execute('DELETE FROM sessions WHERE user_id=?',(target,))
                c.execute("UPDATE products SET status='removed' WHERE seller_id=? AND status='available'",(target,))
                self._settle_banned_orders(c,target,now)
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,target,'ban' if banned else 'unban',reason,now))
        return self.profile(target)

    def _settle_banned_orders(self,c,target,now):
        """封禁账号的在途订单：未付款的直接关闭，已付款但无法交付的转争议并替买家开工单。"""
        for r in c.execute("SELECT * FROM orders WHERE (buyer_id=? OR seller_id=?) AND status='awaiting_payment'",(target,target)).fetchall():
            c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],));self.release(c,r);self.restore_want(c,r)
            self.notify(c,r['buyer_id'],'order_cancelled',f'订单 #{r["id"]} 因账号被处置已关闭，商品释放回在售。',r['id'])
        for r in c.execute("SELECT * FROM orders WHERE seller_id=? AND status IN ('paid','awaiting_handover','awaiting_receipt')",(target,)).fetchall():
            c.execute("UPDATE orders SET status='disputed' WHERE id=?",(r['id'],))
            if not c.execute("SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected')",(r['id'],)).fetchone():
                c.execute("INSERT INTO tickets(user_id,order_id,type,subject,body,status,created) VALUES(?,?,?,?,?,'open',?)",
                          (r['buyer_id'],r['id'],'refund',f'卖家账号被处置，订单 #{r["id"]} 待退款',
                           '该订单卖家账号已被平台处置，无法继续交付。系统已自动转争议，等待客服核实后处理退款。',now))
            self.notify(c,r['buyer_id'],'ticket_refund',f'订单 #{r["id"]} 卖家账号已被处置，已自动转入争议处理，客服会联系你核实退款。',r['id'])
        for r in c.execute("SELECT * FROM orders WHERE buyer_id=? AND status IN ('paid','awaiting_handover')",(target,)).fetchall():
            c.execute("UPDATE orders SET status='cancelled' WHERE id=?",(r['id'],));self.journal(c,r['id'],'refund',r['total'])
            self.release(c,r);self.restore_want(c,r)
            self.notify(c,r['seller_id'],'order_cancelled',f'订单 #{r["id"]} 因买家账号被处置已取消，商品释放回在售。',r['id'])

    def credit_history(self,u):
        return self.rows("SELECT delta,reason,ticket_id,created FROM audit WHERE target=? AND type='credit' ORDER BY id DESC",(u,))

    def audit_log(self,u,kind='',actor=None,since=None,until=None,limit=200):
        """审计查询。

        可见范围是分权的最后一块：**客服只能看自己经手的记录**。
        理由是最小必要——客服需要复核「我昨天那单是怎么处理的」，
        但不需要看到同事和管理员的全部动作，尤其不该看到指向自己的处置记录。
        管理员可以按操作人筛，用于回答「这个客服上个月做了什么」。
        """
        self.staff(u)
        role=self.profile(u)['role']
        limit=max(1,min(int(limit or 200),1000))
        where,args=[],[]
        if role not in ('admin','developer'):
            where.append('a.actor=?');args.append(u)
        elif actor:
            where.append('a.actor=?');args.append(int(actor))
        if kind:
            where.append('a.type=?');args.append(str(kind))
        if since:
            where.append('a.created>=?');args.append(float(since))
        if until:
            where.append('a.created<=?');args.append(float(until))
        sql=('SELECT a.id,a.actor,a.target,a.type,a.delta,a.reason,a.ticket_id,a.created,'
             'u.nickname actor_name FROM audit a LEFT JOIN users u ON u.id=a.actor')
        if where:sql+=' WHERE '+' AND '.join(where)
        sql+=' ORDER BY a.id DESC LIMIT ?';args.append(limit)
        return self.rows(sql,tuple(args))

    def audit_csv(self,u,**kw):
        """导出 CSV。加 BOM，否则 Excel 打开中文是乱码。"""
        import csv, io
        rows=self.audit_log(u,limit=1000,**kw)
        buffer=io.StringIO(newline='')
        writer=csv.writer(buffer)
        writer.writerow(['编号','时间','操作人','操作人昵称','类型','对象用户','分值','理由','工单'])
        import datetime
        for r in rows:
            stamp=datetime.datetime.fromtimestamp(r['created']).strftime('%Y-%m-%d %H:%M:%S') if r['created'] else ''
            writer.writerow([r['id'],stamp,r['actor'],r.get('actor_name') or '',
                             r['type'],r['target'] or '',r['delta'] if r['delta'] is not None else '',
                             r['reason'] or '',r['ticket_id'] or ''])
        return ('\ufeff'+buffer.getvalue()).encode('utf-8')

    @staticmethod
    def mask_phone(phone):
        """账号脱敏。工作台不需要完整账号就能干活；
        真需要联系当事人时再走单独的高敏流程。

        账号现在可能是手机号或邮箱，两者脱敏方式不同：
        手机号保留前 3 位与后 4 位；邮箱保留用户名前 2 位 + 完整域名
        （域名本身不指向个人，保留它才能判断是不是校内邮箱）。"""
        phone=str(phone or '')
        if '@' in phone:
            name,_,domain=phone.partition('@')
            if not domain:return ''
            return (name[:2] if len(name)>2 else name[:1])+'***@'+domain
        return phone[:3]+'****'+phone[-4:] if len(phone)>=7 else ''

    def dossier(self,u,target):
        """用户档案：把「这个人是谁、有没有前科、现在什么状态」集中到一屏，
        不用在工单、商品、审计三处来回翻。

        仅客服与管理员可查，且**每次查阅都写一条审计**——查档案本身就是高敏操作，
        必须能回答「谁在什么时候看了谁」。

        与 /api/profile 的区别：那个是给所有人看的公开主页（已收敛掉 role/status），
        这个只在服务端开放，可以带 role、status、脱敏手机号和订单。
        """
        self.staff(u);target=int(target)
        user=self.profile(target)
        now=time.time()
        with self.tx() as c:
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',(u,target,'dossier_view','查阅用户档案',now))
        phone=self.row('SELECT phone FROM users WHERE id=?',(target,))
        orders=self.rows('SELECT id,buyer_id,seller_id,status,total,created FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT 50',(target,target))
        for o in orders:o['role']='buyer' if o['buyer_id']==target else 'seller'
        return {
            'user':user,
            'phone':self.mask_phone(phone['phone'] if phone else ''),
            'orders':orders,
            'products':self.my_products(target),
            'tickets':self.rows('SELECT id,type,subject,status,order_id,product_id,created FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 50',(target,)),
            'audit':self.rows('SELECT id,actor,target,type,delta,reason,ticket_id,created FROM audit WHERE target=? ORDER BY id DESC LIMIT 100',(target,)),
            'served_by':u,
        }

    def review(self,u,oid,rating,body):
        o=self.order(u,oid);self.require(o['status']=='completed' and u in [o['buyer_id'],o['seller_id']],'完成真实有效订单后才能评价')
        self.require(type(rating) is int and 1<=rating<=5,'评分需1至5分')
        with self.tx() as c:
            c.execute('INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?) ON CONFLICT(order_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body',(oid,u,rating,self.text(body,500,'评价'),time.time()))
        return {'ok':True,'simulation':True}
