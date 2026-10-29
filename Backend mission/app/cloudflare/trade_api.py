"""Existing simulated trade rules using conditional, atomic D1 batches."""
import json
import secrets
import time
from ..core.errors import ValidationMixin, DomainError
from .http import json_body, json_response, query_of, int_param, require


class TradeApi:
    @staticmethod
    def cf_trade_note(uid, kind, body, oid=None, tid=None):
        return ('INSERT INTO notifications(user_id,kind,order_id,ticket_id,body,created) VALUES(?,?,?,?,?,?)',
                (uid, kind, oid, tid, body, time.time()))

    @staticmethod
    def cf_trade_journal(oid, kind, amount, now):
        return ('INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',
                (oid, kind, amount, now))

    @staticmethod
    def cf_trade_guard(row):
        return ('SELECT 1 FROM orders WHERE id=? AND status=? AND items=? AND total=? '
                "AND COALESCE(schedule_confirmed,0)=? AND COALESCE(appointment,0)=? AND COALESCE(address,'')=?",
                (row['id'], row['status'], row['items'], row['total'], row.get('schedule_confirmed') or 0,
                 row.get('appointment') or 0, row.get('address') or ''))

    async def cf_trade_dto(self, row):
        result = dict(row)
        result['items'] = json.loads(result.get('items') or '[]')
        oid = row['id']
        for key, sql in [
            ('ledger', 'SELECT kind,amount,created FROM ledger WHERE order_id=? ORDER BY id'),
            ('changes', 'SELECT * FROM order_changes WHERE order_id=? ORDER BY id DESC'),
            ('notes', 'SELECT * FROM order_notes WHERE order_id=? ORDER BY id DESC')]:
            result[key] = await self.db.all(sql, (oid,))
        for role in ('buyer', 'seller'):
            result[role] = await self.db.scalar('SELECT nickname FROM users WHERE id=?', (row[role+'_id'],)) or '已注销用户'
        return result

    async def cf_trade_read_order(self, uid, oid):
        row = await self.db.first('SELECT * FROM orders WHERE id=?', (oid,))
        require(row is not None, '订单不存在', 404)
        role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        require(uid in (row['buyer_id'], row['seller_id']) or role in ('support', 'admin', 'developer'),
                '不能查看他人订单', 403)
        return row

    async def cf_trade_order(self, request):
        uid = await self.page_user(request)
        row = await self.cf_trade_read_order(uid, int_param(query_of(request), 'id'))
        return json_response(await self.cf_trade_dto(row))

    async def cf_trade_checkout(self, request):
        uid = await self.page_user(request)
        await self.require_capacity()
        data = await json_body(request)
        ids = data.get('product_ids')
        require(isinstance(ids, list) and 1 <= len(ids) <= 20
                and all(type(i) is int and i > 0 for i in ids) and len(set(ids)) == len(ids),
                '请选择1至20件不同商品')
        key = ValidationMixin.text(data.get('key'), 100, '请求标识')
        delivery = data.get('delivery')
        require(delivery in ('pickup', 'delivery'), '交付方式错误')
        appointment = data.get('appointment')
        now = time.time()
        require(type(appointment) in (int, float) and now+60 < appointment < now+86400*30,
                '请选择未来30天内的交付时间')
        address = ValidationMixin.text(data.get('address'), 150, '收货公共地点') if delivery == 'delivery' else ''
        old = await self.db.first('SELECT * FROM orders WHERE buyer_id=? AND request_key=?', (uid, key))
        if old:
            # 幂等键只保证「同一次提交重试」返回同一张单；若内容变了还返回旧单，
            # 用户会以为买的是新商品，实际拿到的是上一笔。必须 409 让他刷新重来。
            old_ids = sorted(i.get('id') for i in json.loads(old['items'] or '[]'))
            same = (old_ids == sorted(ids) and old['delivery'] == delivery
                    and (old['address'] or '') == (address or '')
                    and abs((old['appointment'] or 0) - float(appointment)) < 1e-6)
            require(same, '同一请求标识不能提交不同内容，请刷新后重试', 409)
            return json_response(await self.cf_trade_dto(old))
        require(await self.db.scalar("SELECT 1 FROM users WHERE id=? AND status='active'", (uid,)),
                '账号当前不可交易', 409)
        marks = ','.join('?' for _ in ids)
        products = await self.db.all('SELECT * FROM products WHERE id IN ('+marks+') ORDER BY id', tuple(ids))
        require(len(products) == len(ids), '商品不存在', 404)
        seller = products[0]['seller_id']
        require(all(p['seller_id'] == seller for p in products), '只能合并同一卖家的商品')
        require(seller != uid, '不能购买自己的商品')
        require(all(p['status'] == 'available' for p in products), '部分商品已被预留或售出', 409)
        require(all(p['delivery'] in (delivery, 'both') for p in products), '商品不支持所选交付方式')
        require(await self.db.scalar("SELECT 1 FROM users WHERE id=? AND status='active'", (seller,)),
                '卖家当前不可交易', 409)
        guards = ["EXISTS(SELECT 1 FROM users WHERE id=? AND status='active')",
                  "EXISTS(SELECT 1 FROM users WHERE id=? AND status='active')"]
        guard_args = [seller, uid]
        live_since = now - 86400
        items = []
        for p in products:
            # 接受超过 24 小时未成交的报价不再生效；其他买家有生效中的接受报价时，
            # 商品已被锁定，本买家不能抢先下单（一货多卖的最后一道闸）。
            require(not await self.db.first(
                "SELECT 1 FROM offers WHERE product_id=? AND buyer_id<>? AND status='accepted' AND COALESCE(accepted_at,created)>? LIMIT 1",
                (p['id'], uid, live_since)), '该商品已有其他买家的报价被接受，正在等待成交', 409)
            offer = await self.db.first(
                "SELECT id,amount FROM offers WHERE product_id=? AND buyer_id=? AND status='accepted' "
                "AND COALESCE(accepted_at,created)>? ORDER BY id DESC LIMIT 1",
                (p['id'], uid, live_since))
            price = offer['amount'] if offer else p['price']
            detail = json.loads(p['data'] or '{}')
            photos = detail.get('photos') or []
            require(photos, '商品照片不完整，请联系卖家')
            item = {k: detail.get(k, '') for k in ('edition', 'notes', 'missing', 'accessories')}
            item.update(id=p['id'], title=p['title'], price=price, region=p['region'], photo=photos[0]['url'])
            items.append(item)
            guards.append("EXISTS(SELECT 1 FROM products WHERE id=? AND seller_id=? AND status='available' "
                          'AND price=? AND delivery_fee=? AND delivery=? AND data=?)')
            guard_args.extend((p['id'], seller, p['price'], p['delivery_fee'], p['delivery'], p['data']))
            guards.append("COALESCE((SELECT id FROM offers WHERE product_id=? AND buyer_id=? AND status='accepted' "
                          "AND COALESCE(accepted_at,created)>? ORDER BY id DESC LIMIT 1),0)=?")
            guard_args.extend((p['id'], uid, live_since, offer['id'] if offer else 0))
            guards.append("NOT EXISTS(SELECT 1 FROM offers WHERE product_id=? AND buyer_id<>? AND status='accepted' "
                          "AND COALESCE(accepted_at,created)>?)")
            guard_args.extend((p['id'], uid, live_since))
        want = None
        if data.get('want_id') is not None:
            require(type(data['want_id']) is int and data['want_id'] > 0, '求购编号无效')
            want = await self.db.first("SELECT * FROM wants WHERE id=? AND status='open'", (data['want_id'],))
            require(want is not None, '该求购已成交或不存在')
            require(want['user_id'] == uid, '不能替他人完成求购', 403)
            guards.append("EXISTS(SELECT 1 FROM wants WHERE id=? AND user_id=? AND status='open')")
            guard_args.extend((want['id'], uid))
        subtotal = sum(i['price'] for i in items)
        fee = max(p['delivery_fee'] for p in products) if delivery == 'delivery' else 0
        oid = secrets.randbits(48)
        stmts = [('INSERT INTO orders(id,buyer_id,seller_id,items,subtotal,delivery_fee,total,delivery,address,appointment,status,created,request_key,want_id) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (oid, uid, seller, json.dumps(items, ensure_ascii=False), subtotal, fee, subtotal+fee, delivery,
                   address, appointment, 'awaiting_payment', now, key, want['id'] if want else None))]
        stmts += [("UPDATE products SET status='reserved' WHERE id=?", (p['id'],)) for p in products]
        if want:
            stmts.extend([("UPDATE wants SET status='matched' WHERE id=?", (want['id'],)),
                          self.cf_trade_journal(oid, 'service_fee', subtotal*5//100, now)])
        stmts.append(self.cf_trade_note(seller, 'order_created', f'收到新订单 #{oid}，等待买家模拟付款。', oid))
        try:
            await self.db.guarded_batch('SELECT 1 WHERE '+' AND '.join(guards), tuple(guard_args), stmts,
                                        '商品、报价或求购状态已变化，请重新确认')
        except Exception:
            existing = await self.db.first('SELECT * FROM orders WHERE buyer_id=? AND request_key=?', (uid, key))
            if existing:
                return json_response(await self.cf_trade_dto(existing))
            raise
        return json_response(await self.cf_trade_dto(await self.db.first('SELECT * FROM orders WHERE id=?', (oid,))))

    def cf_trade_release(self, row, items=None):
        return [("UPDATE products SET status=CASE WHEN EXISTS(SELECT 1 FROM users u WHERE u.id=products.seller_id "
                 "AND u.status='active') THEN 'available' ELSE 'removed' END,promoted_until=0 "
                 "WHERE id=? AND status='reserved'", (item['id'],))
                for item in (items if items is not None else json.loads(row['items'] or '[]'))]

    def cf_trade_restore_want(self, row, now):
        if not row.get('want_id'):
            return []
        return [("UPDATE wants SET status='open' WHERE id=? AND status='matched'", (row['want_id'],)),
                ("INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) SELECT order_id,'service_fee_reversal',amount,? "
                 "FROM ledger WHERE order_id=? AND kind='service_fee'", (now, row['id']))]

    def cf_trade_complete(self, row, now):
        oid = row['id']
        return [("UPDATE orders SET status='completed',completed_at=? WHERE id=?", (now, oid)),
                self.cf_trade_journal(oid, 'settlement', row['total'], now),
                *[("UPDATE products SET status='sold',promoted_until=0 WHERE id=?", (i['id'],)) for i in json.loads(row['items'])],
                self.cf_trade_note(row['seller_id'], 'order_completed', f'订单 #{oid} 已确认收货，模拟结算完成。', oid)]

    async def cf_trade_refund_statements(self, row, amount, now):
        amount = ValidationMixin.cents(amount, '退款金额')
        require(0 < amount <= row['total'], '退款不能超过订单金额')
        oid = row['id']
        settled = await self.db.scalar("SELECT amount FROM ledger WHERE order_id=? AND kind='settlement'", (oid,))
        stmts = [self.cf_trade_journal(oid, 'refund', amount, now)]
        if settled is not None:
            stmts.append(self.cf_trade_journal(oid, 'settlement_reversal', min(amount, settled), now))
        elif amount < row['total']:
            stmts.append(self.cf_trade_journal(oid, 'settlement', row['total']-amount, now))
        stmts.append(('UPDATE orders SET status=? WHERE id=?',
                      ('refunded' if amount >= row['total'] else 'partial_refunded', oid)))
        stmts += [("UPDATE products SET status='removed',promoted_until=0 WHERE id=?", (i['id'],)) for i in json.loads(row['items'])]
        stmts += self.cf_trade_restore_want(row, now)
        for target in (row['buyer_id'], row['seller_id']):
            stmts.append(self.cf_trade_note(target, 'refund_done', f'订单 #{oid} 已完成模拟退款，请查看工单结论。', oid))
        return stmts

    async def cf_trade_action(self, request):
        uid = await self.page_user(request)
        data = await json_body(request)
        require(type(data.get('id')) is int, '订单编号无效')
        row = await self.cf_trade_read_order(uid, data['id'])
        require(uid in (row['buyer_id'], row['seller_id']), '不能处理他人订单', 403)
        buyer = uid == row['buyer_id']; action = data.get('action'); status = row['status']; now = time.time(); oid = row['id']
        guard, params = self.cf_trade_guard(row)
        stmts = []
        if action == 'pay':
            require(buyer, '仅买家可付款', 403)
            if status in ('paid', 'awaiting_handover', 'awaiting_receipt', 'completed'):
                return json_response(await self.cf_trade_dto(row))
            require(status == 'awaiting_payment' and now-row['created'] < 1800, '订单不可付款或已超时', 409)
            guard += (" AND EXISTS(SELECT 1 FROM users WHERE id=? AND status='active')"
                      " AND EXISTS(SELECT 1 FROM users WHERE id=? AND status='active')")
            params += (uid, row['seller_id'])
            stmts += [("UPDATE orders SET status='paid',paid_at=? WHERE id=?", (now, oid)),
                      self.cf_trade_journal(oid, 'payment', row['total'], now),
                      self.cf_trade_note(row['seller_id'], 'order_paid', f'订单 #{oid} 已模拟付款，请确认交付安排。', oid)]
        elif action == 'cancel':
            require(buyer or status == 'awaiting_payment', '卖家只能在付款前取消，已付款请走客服流程', 403)
            require(status in ('awaiting_payment', 'paid', 'cancelled'), '已交付或存在争议，请申请售后')
            if status == 'cancelled':
                return json_response(await self.cf_trade_dto(row))
            if status == 'paid':
                stmts.append(self.cf_trade_journal(oid, 'refund', row['total'], now))
            stmts += [("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))]
            stmts += self.cf_trade_release(row)+self.cf_trade_restore_want(row, now)
            stmts.append(self.cf_trade_note(row['seller_id'] if buyer else row['buyer_id'], 'order_cancelled', f'订单 #{oid} 已取消。', oid))
        elif action == 'deliver':
            require(not buyer and status == 'paid', '仅卖家可在付款后标记交付', 403)
            stmts += [("UPDATE orders SET status='awaiting_handover',schedule_confirmed=1,delivered_at=? WHERE id=?", (now, oid)),
                      self.cf_trade_note(row['buyer_id'], 'order_delivered', f'订单 #{oid} 卖家已标记交付，请核对实物后确认交接。', oid)]
        elif action == 'handover':
            require(buyer and status == 'awaiting_handover', '请在实际交接后确认')
            stmts += [("UPDATE orders SET status='awaiting_receipt',handover_at=? WHERE id=?", (now, oid)),
                      self.cf_trade_note(row['seller_id'], 'order_handover', f'订单 #{oid} 已确认交接，24小时后自动收货。', oid)]
        elif action == 'receive':
            require(buyer and status in ('awaiting_receipt', 'completed'), '请先核对交接再确认收货')
            if status == 'completed':
                return json_response(await self.cf_trade_dto(row))
            guard += " AND NOT EXISTS(SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected'))"
            params += (oid,)
            stmts += self.cf_trade_complete(row, now)
        elif action == 'confirm_schedule':
            require(not buyer and status == 'paid', '仅卖家可在付款后确认时间')
            stmts.append(('UPDATE orders SET schedule_confirmed=1 WHERE id=?', (oid,)))
        elif action == 'reschedule':
            require(status in ('paid', 'awaiting_handover'), '当前不能申请改约')
            at = data.get('appointment')
            require(type(at) in (int, float) and now+60 < at < now+86400*30, '请选择未来30天内的改约时间')
            address = ValidationMixin.text(data.get('address') or row['address'] or json.loads(row['items'])[0]['region'], 150, '改约地点')
            guard += " AND NOT EXISTS(SELECT 1 FROM order_changes WHERE order_id=? AND status='pending')"
            params += (oid,)
            stmts += [('INSERT INTO order_changes(id,order_id,proposer,appointment,address,created) VALUES(?,?,?,?,?,?)',
                       (secrets.randbits(48), oid, uid, at, address, now)),
                      self.cf_trade_note(row['seller_id'] if buyer else row['buyer_id'], 'order_reschedule', f'订单 #{oid} 有新的改约申请。', oid)]
        else:
            require(False, '不支持此订单操作')
        await self.db.guarded_batch(guard, params, stmts, '订单已更新，请刷新后重试')
        return json_response(await self.cf_trade_dto(await self.db.first('SELECT * FROM orders WHERE id=?', (oid,))))

    async def cf_trade_update(self, request):
        uid = await self.page_user(request); data = await json_body(request)
        require(type(data.get('id')) is int, '订单编号无效')
        row = await self.cf_trade_read_order(uid, data['id'])
        buyer = uid == row['buyer_id']
        require(uid in (row['buyer_id'], row['seller_id']), '不能修改他人订单', 403)
        require(row['status'] == 'awaiting_payment', '付款后请通过改约或售后修改')
        original = json.loads(row['items']); items = original; removed = []
        if 'product_ids' in data:
            require(buyer, '仅买家可调整商品', 403)
            keep = data['product_ids']
            require(isinstance(keep, list) and keep and all(type(i) is int for i in keep)
                    and len(keep) == len(set(keep)) and set(keep).issubset({i['id'] for i in original}), '订单商品无效')
            items = [i for i in original if i['id'] in keep]; removed = [i for i in original if i['id'] not in keep]
        delivery = data.get('delivery') or row['delivery']
        require(delivery in ('pickup', 'delivery'), '交付方式无效')
        require(buyer or ('delivery' not in data and 'address' not in data), '仅买家可更改交付方式和地点', 403)
        products = [await self.db.first('SELECT * FROM products WHERE id=?', (i['id'],)) for i in items]
        require(all(p and p['delivery'] in (delivery, 'both') for p in products), '商品不支持所选交付方式')
        address = ValidationMixin.text(data.get('address', row['address']), 150, '公共交付地点') if delivery == 'delivery' else ''
        at = data.get('appointment', row['appointment']); now = time.time()
        require(type(at) in (int, float) and now+60 < at < now+86400*30, '请选择未来30天内的交付时间')
        subtotal = sum(i['price'] for i in items); fee = max(p['delivery_fee'] for p in products) if delivery == 'delivery' else 0
        oid = row['id']; guard, params = self.cf_trade_guard(row)
        stmts = [('UPDATE orders SET items=?,subtotal=?,delivery_fee=?,total=?,delivery=?,address=?,appointment=? WHERE id=?',
                  (json.dumps(items, ensure_ascii=False), subtotal, fee, subtotal+fee, delivery, address, at, oid))]
        stmts += self.cf_trade_release(row, removed)
        stmts += [('INSERT INTO order_notes(order_id,user_id,body,created) VALUES(?,?,?,?)',
                   (oid, uid, '买家移除商品：'+i['title'], now)) for i in removed]
        if row.get('want_id'):
            stmts.append(("UPDATE ledger SET amount=? WHERE order_id=? AND kind='service_fee'", (subtotal*5//100, oid)))
        if buyer:
            stmts.append(self.cf_trade_note(row['seller_id'], 'order_updated', f'订单 #{oid} 买家修改了商品或交付信息。', oid))
        await self.db.guarded_batch(guard, params, stmts)
        return json_response(await self.cf_trade_dto(await self.db.first('SELECT * FROM orders WHERE id=?', (oid,))))

    async def cf_trade_change(self, request):
        uid = await self.page_user(request); data = await json_body(request)
        require(type(data.get('id')) is int and type(data.get('accept')) is bool, '改约参数无效')
        change = await self.db.first('SELECT * FROM order_changes WHERE id=?', (data['id'],))
        require(change is not None, '改约不存在', 404)
        row = await self.cf_trade_read_order(uid, change['order_id'])
        require(uid in (row['buyer_id'], row['seller_id']) and uid != change['proposer'], '仅交易另一方可确认改约', 403)
        require(row['status'] in ('paid', 'awaiting_handover') and change['status'] == 'pending', '改约已失效', 409)
        require(not data['accept'] or change['appointment'] > time.time()+60, '该时段已过期')
        guard, params = self.cf_trade_guard(row)
        guard += " AND EXISTS(SELECT 1 FROM order_changes WHERE id=? AND status='pending')"
        params += (change['id'],)
        stmts = [('UPDATE order_changes SET status=? WHERE id=?', ('accepted' if data['accept'] else 'rejected', change['id']))]
        if data['accept']:
            stmts.append(('UPDATE orders SET appointment=?,address=?,schedule_confirmed=1 WHERE id=?',
                          (change['appointment'], change['address'], row['id'])))
        stmts.append(self.cf_trade_note(change['proposer'], 'order_change_result', f'订单 #{row["id"]} 改约已被处理。', row['id']))
        await self.db.guarded_batch(guard, params, stmts)
        return json_response({'ok': True})

    async def cf_trade_tick(self, now=None):
        now = now or time.time(); changed = 0
        rows = await self.db.all("SELECT * FROM orders WHERE (status='awaiting_payment' AND created<?) OR "
                                 "(status='paid' AND schedule_confirmed=0 AND COALESCE(paid_at,created)<?) OR "
                                 "(status='awaiting_receipt' AND handover_at<?)", (now-1800, now-86400, now-86400))
        for row in rows:
            guard, params = self.cf_trade_guard(row); oid = row['id']
            if row['status'] == 'awaiting_receipt':
                guard += " AND NOT EXISTS(SELECT 1 FROM tickets WHERE order_id=? AND type='refund' AND status NOT IN ('resolved','rejected'))"
                params += (oid,); stmts = self.cf_trade_complete(row, now)
            else:
                stmts = [("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))]
                if row['status'] == 'paid':
                    stmts.append(self.cf_trade_journal(oid, 'refund', row['total'], now))
                stmts += self.cf_trade_release(row)+self.cf_trade_restore_want(row, now)
                for target in (row['buyer_id'], row['seller_id']):
                    stmts.append(self.cf_trade_note(target, 'order_timeout', f'订单 #{oid} 已超时关闭。', oid))
            try:
                await self.db.guarded_batch(guard, params, stmts)
                changed += 1
            except DomainError as exc:
                if exc.status != 409:
                    raise
        await self.db.batch([
            ('DELETE FROM sessions WHERE expires<?', (now,)),
            ('DELETE FROM otp WHERE expires<?', (now-86400,)),
            ('DELETE FROM auth_attempts WHERE reset_at<?', (now-86400,)),
            ("UPDATE offers SET status='rejected' WHERE status='accepted' AND accepted_at<?", (now-86400,)),
            # 客服会话 30 分钟无新消息自动结束（用户关页面 / 客服下班），
            # 归档消息后双方会话列表都不再显示，重新咨询开新一轮。
            ("UPDATE rooms SET support_status='closed',support_closed_at=?,support_closed_by='timeout',assignee=0 "
             "WHERE support=1 AND COALESCE(support_status,'open')='open' "
             "AND COALESCE((SELECT MAX(created) FROM messages WHERE room_id=rooms.id AND removed<>3),0)<?", (now, now-1800)),
            ("UPDATE messages SET removed=3 WHERE removed IN (0,1) AND room_id IN "
             "(SELECT id FROM rooms WHERE support=1 AND support_status='closed' AND support_closed_by='timeout' AND support_closed_at=?)", (now,))])
        # 工单 SLA 与订单超时共用这次定时任务，避免再开一个调度器。
        await self.cf_ticket_sla_notices(now)
        return {'ok': True, 'processed': changed}


TRADE_ROUTES = {
    '/api/checkout': (('POST',), 'cf_trade_checkout'),
    '/api/order': (('GET',), 'cf_trade_order'),
    '/api/order/action': (('POST',), 'cf_trade_action'),
    '/api/order/update': (('POST',), 'cf_trade_update'),
    '/api/order/change': (('POST',), 'cf_trade_change'),
}
