"""Operator workflows scoped to this domain."""
import json
import time
import uuid
from decimal import Decimal


class PhysicalReturns:
    def return_action(self, user_id, ticket_id, action):
        ticket = self.ticket(user_id, ticket_id)
        self.require(ticket['type'] == 'refund' and ticket['refund_mode'] == 'return_refund', '该工单不是退货退款')
        with self.tx() as connection:
            ticket = connection.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            self.require(ticket['status'] != 'resolved', '售后已结束')
            order = connection.execute('SELECT * FROM orders WHERE id=?', (ticket['order_id'],)).fetchone()
            self.require(order['delivered_at'], '尚未交付，无需退回实物')
            if action == 'return_sent':
                self.require(user_id == order['buyer_id'], '仅买家可标记已退回', 403)
                connection.execute('UPDATE tickets SET return_sent_at=COALESCE(return_sent_at,?) WHERE id=?',
                                   (time.time(), ticket_id))
            elif action == 'confirm_return':
                self.require(user_id == order['seller_id'], '仅卖家可确认收到实物', 403)
                self.require(ticket['return_sent_at'], '请先由买家记录已退回')
                connection.execute('UPDATE tickets SET return_received_at=COALESCE(return_received_at,?) WHERE id=?',
                                   (time.time(), ticket_id))
            else:
                self.require(False, '无效退货操作')
            connection.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',
                               (user_id, action, '交易当事人确认实物退回进度', ticket_id, time.time()))
            self.notify_ticket(connection,ticket_id,f'ticket:{ticket_id}:{action}','退货交接进度已更新',actor=user_id)
        return self.ticket(user_id, ticket_id)

    def _relist_source(self, connection, user_id, product_id):
        source = connection.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        self.require(source and source['seller_id'] == user_id, '商品不存在或不属于你', 403)
        self.require(source['status'] == 'removed', '该商品仍在售、交易中或已售出')
        eligible = False
        tickets = connection.execute(
            "SELECT o.items FROM tickets t JOIN orders o ON o.id=t.order_id WHERE o.seller_id=? "
            "AND o.status='refunded' AND t.status='resolved' AND t.outcome='refund' "
            "AND t.refund_mode='return_refund' AND t.return_received_at IS NOT NULL", (user_id,),
        ).fetchall()
        for row in tickets:
            if any(item['id'] == product_id for item in json.loads(row['items'])):
                eligible = True
                break
        self.require(eligible, '仅退款不恢复库存；须收到退货、退款完成且争议结束后重新上架')
        stock_key = source['stock_key'] or 'legacy:' + str(product_id)
        latest = connection.execute('SELECT MAX(id) AS id FROM products WHERE stock_key=?', (stock_key,)).fetchone()
        self.require(latest['id'] in (None, product_id), '该物品已有更新的出售记录，请查看最新商品的实物去向', 409)
        held = connection.execute("SELECT id FROM products WHERE stock_key=? AND status IN ('available','reserved','sold')",
                                  (stock_key,)).fetchone()
        self.require(not held, '这件实物已经重新上架、被预订或再次售出', 409)
        if not source['stock_key']:
            connection.execute('UPDATE products SET stock_key=? WHERE id=?', (stock_key, product_id))
            source = connection.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        return source

    def relist_draft(self, user_id, product_id):
        with self.tx() as connection:
            source = self._relist_source(connection, user_id, product_id)
            existing = connection.execute(
                "SELECT id FROM drafts WHERE user_id=? AND source_product_id=? AND status='active' AND updated_at>?",
                (user_id, product_id, time.time() - 30 * 86400),
            ).fetchone()
            if existing:
                draft_id = existing['id']
            else:
                data = json.loads(source['data'])
                fields = {name: str(data.get(name) or '') for name in [
                    'edition', 'publisher', 'notes', 'missing', 'accessories', 'bought', 'condition',
                    'author', 'isbn', 'course', 'major', 'college', 'description',
                ]}
                fields.update({name: source[name] for name in ['title', 'category', 'delivery', 'region']})
                fields['price'] = format(Decimal(source['price']) / 100, '.2f')
                fields['delivery_fee'] = format(Decimal(source['delivery_fee']) / 100, '.2f')
                fields['photos'] = [photo['id'] for photo in data.get('photos', [])]
                draft_id = uuid.uuid4().hex
                connection.execute('INSERT INTO drafts(id,user_id,fields,updated_at,source_product_id) VALUES(?,?,?,?,?)',
                                   (draft_id, user_id, json.dumps(fields, ensure_ascii=False), time.time(), product_id))
        return self.get_draft(user_id, draft_id)

    def seller_products(self, user_id):
        result = []
        for row in self.rows('SELECT id FROM products WHERE seller_id=? ORDER BY id DESC', (user_id,)):
            product = self.product(row['id'], user_id)
            product['can_relist'] = False
            if product['status'] == 'removed':
                with self.tx() as connection:
                    try:
                        self._relist_source(connection, user_id, product['id'])
                        product['can_relist'] = True
                    except Exception as error:
                        if not hasattr(error, 'status'):
                            raise
                        product['relist_reason'] = str(error)
            result.append(product)
        return result
