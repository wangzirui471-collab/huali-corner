"""Async read adapters for existing personal and staff pages.

No schema migration or order/stock writes. Existing JSON shapes and ownership
checks are retained; domain mutation adapters are registered separately.
"""
import json
import time

from . import sessions
from .http import int_param, json_body, json_response, query_of, require


class ReadPages:
    async def page_user(self, request, staff=False):
        uid = await sessions.require_user_id(self.db, request)
        if staff:
            role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
            require(role in ('support', 'admin', 'developer'), '没有客服权限', 403)
        return uid

    async def health(self, request):
        await self.db.scalar('SELECT 1')
        return json_response({'ok': True, 'trial': True})

    async def listing_dto(self, row):
        item = dict(row)
        detail = json.loads(item.pop('data', None) or '{}')
        detail.pop('proof', None)
        moderation = detail.pop('moderation', None)
        item.update(detail)
        item['under_review'] = bool(moderation and not moderation.get('reviewed'))
        return item

    async def listings_response(self, request, removed=False):
        uid = await self.page_user(request, staff=removed)
        where, args = ("p.status='removed'", ()) if removed else ('p.seller_id=?', (uid,))
        status = query_of(request).get('status')
        if status and not removed:
            where += ' AND p.status=?'
            args += (status,)
        rows = await self.db.all(
            'SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p '
            'JOIN users u ON u.id=p.seller_id WHERE '+where+' ORDER BY p.id DESC', args)
        disputed = await self.db.all(
            "SELECT items FROM orders WHERE status IN ('refunded','partial_refunded','disputed')")
        locked = {int(i['id']) for order in disputed for i in json.loads(order['items'] or '[]')}
        items = []
        for row in rows:
            item = await self.listing_dto(row)
            if item['status'] == 'removed':
                reason = ('平台处置下架，需客服复核' if item.get('delisted_by') else
                          '卷入退款或争议，需客服复核' if item['id'] in locked else
                          '信誉分低于60，暂不能上架' if item['score'] < 60 else '')
                item.update(relist_locked=bool(reason), lock_reason=reason)
            items.append(item)
        return json_response(items)

    async def my_products(self, request):
        return await self.listings_response(request)

    async def removed_products(self, request):
        return await self.listings_response(request, removed=True)

    async def orders(self, request):
        uid = await self.page_user(request)
        rows = await self.db.all(
            'SELECT o.*,b.nickname buyer,s.nickname seller FROM orders o '
            'JOIN users b ON b.id=o.buyer_id JOIN users s ON s.id=o.seller_id '
            'WHERE o.buyer_id=? OR o.seller_id=? ORDER BY o.id DESC', (uid, uid))
        for row in rows:
            row['items'] = json.loads(row['items'] or '[]')
            oid = row['id']
            row['ledger'] = await self.db.all(
                'SELECT kind,amount,created FROM ledger WHERE order_id=? ORDER BY id', (oid,))
            row['changes'] = await self.db.all(
                'SELECT * FROM order_changes WHERE order_id=? ORDER BY id DESC', (oid,))
            row['notes'] = await self.db.all(
                'SELECT * FROM order_notes WHERE order_id=? ORDER BY id DESC', (oid,))
        return json_response(rows)

    async def offers(self, request):
        uid = await self.page_user(request)
        return json_response(await self.db.all(
            'SELECT o.*,p.title,p.seller_id,u.nickname FROM offers o '
            'JOIN products p ON p.id=o.product_id JOIN users u ON u.id=o.buyer_id '
            'WHERE o.buyer_id=? OR p.seller_id=? ORDER BY o.id DESC', (uid, uid)))

    async def notifications(self, request):
        uid = await self.page_user(request)
        if request.method == 'POST':
            data = await json_body(request)
            nid = data.get('id')
            if nid:
                require(type(nid) is int and nid > 0, '通知编号无效')
                await self.db.run('UPDATE notifications SET read_at=? WHERE id=? AND user_id=?',
                                  (time.time(), nid, uid))
            else:
                await self.db.run('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',
                                  (time.time(), uid))
            return json_response({'ok': True})
        items = await self.db.all(
            'SELECT id,kind,order_id,ticket_id,post_id,body,read_at,created FROM notifications '
            'WHERE user_id=? ORDER BY id DESC LIMIT 100', (uid,))
        count = await self.db.scalar(
            'SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL', (uid,))
        return json_response({'unread': count or 0, 'items': items})

    async def badges(self, request):
        uid = await self.page_user(request)
        unread = await self.db.scalar(
            'SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL', (uid,))
        chat = await self.db.scalar(
            'SELECT COUNT(*) FROM messages m JOIN members x ON x.room_id=m.room_id '
            'WHERE x.user_id=? AND m.id>x.last_read_id AND m.user_id<>? AND m.removed=0 '
            'AND NOT EXISTS(SELECT 1 FROM message_hides h WHERE h.user_id=? AND h.message_id=m.id)',
            (uid, uid, uid))
        return json_response({'notifications': unread or 0, 'chat': chat or 0})

    async def public_profile(self, request):
        who = int_param(query_of(request), 'id')
        profile = await self.profile_dto(who)
        fields = ('id', 'nickname', 'college', 'major', 'education', 'bio', 'score', 'avatar_url')
        user = {key: profile[key] for key in fields}
        user['trusted'] = (await self.trusted_map([who])).get(who, False)
        rows = await self.db.all(
            "SELECT p.*,u.nickname,u.college seller_college,u.score FROM products p "
            "JOIN users u ON u.id=p.seller_id WHERE p.seller_id=? AND p.status='available' "
            "ORDER BY p.id DESC", (who,))
        viewer, _ = await sessions.current_user_id(self.db, request)
        products = []
        for row in rows:
            item = await self.listing_dto(row)
            item['seller_trusted'] = user['trusted']
            item['likes'] = await self.db.scalar(
                "SELECT COUNT(*) FROM reactions WHERE product_id=? AND kind='like'", (item['id'],)) or 0
            for key, kind in [('liked', 'like'), ('favorited', 'favorite')]:
                item[key] = bool(viewer and await self.db.first(
                    'SELECT 1 FROM reactions WHERE product_id=? AND user_id=? AND kind=?',
                    (item['id'], viewer, kind)))
            products.append(item)
        return json_response({'user': user, 'products': products})

    async def user_profile(self, request):
        uid = await self.page_user(request)
        return json_response(await self.profile_dto(uid))

    async def tickets(self, request):
        uid = await self.page_user(request)
        staff = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        if staff in ('support', 'admin', 'developer'):
            where, args = '1=1', ()
        else:
            where, args = '(t.user_id=? OR o.buyer_id=? OR o.seller_id=?)', (uid, uid, uid)
        rows = await self.db.all(
            'SELECT t.*,u.nickname FROM tickets t JOIN users u ON u.id=t.user_id '
            'LEFT JOIN orders o ON o.id=t.order_id WHERE '+where+' ORDER BY t.id DESC', args)
        return json_response(rows)

    async def audit_rows(self, uid, query):
        where, args = [], []
        role = await self.db.scalar('SELECT role FROM users WHERE id=?', (uid,))
        if role == 'support':
            where.append('a.actor=?'); args.append(uid)
        elif query.get('actor'):
            where.append('a.actor=?'); args.append(int_param(query, 'actor'))
        for name, column, operator in [('type', 'a.type', '='), ('since', 'a.created', '>='),
                                        ('until', 'a.created', '<=')]:
            if query.get(name):
                where.append(column+operator+'?'); args.append(query[name])
        limit = max(1, min(int_param(query, 'limit', required=False) or 100, 1000))
        sql = 'SELECT a.*,u.nickname actor_name FROM audit a LEFT JOIN users u ON u.id=a.actor'
        if where:
            sql += ' WHERE '+' AND '.join(where)
        return await self.db.all(sql+' ORDER BY a.id DESC LIMIT ?', tuple(args)+(limit,))

    async def audit(self, request):
        uid = await self.page_user(request, staff=True)
        return json_response(await self.audit_rows(uid, query_of(request)))

    async def admin_overview(self, request):
        uid = await self.page_user(request, staff=True)
        users = await self.db.all('SELECT id,nickname,college,score,role,status FROM users')
        nominations = await self.db.all(
            'SELECT n.*,u.nickname,r.name FROM nominations n JOIN users u ON u.id=n.user_id '
            'JOIN rooms r ON r.id=n.room_id')
        return json_response({'users': users, 'audit': await self.audit_rows(uid, {}),
                              'nominations': nominations})

    async def reconcile(self, request):
        await self.page_user(request, staff=True)
        orders = await self.db.all('SELECT id,total,status FROM orders ORDER BY id DESC')
        for row in orders:
            entries = await self.db.all('SELECT kind,amount FROM ledger WHERE order_id=?', (row['id'],))
            amounts = {entry['kind']: entry['amount'] for entry in entries}
            net = amounts.get('settlement', 0)-amounts.get('settlement_reversal', 0)
            held = amounts.get('payment', 0)-amounts.get('refund', 0)-net
            closed = row['status'] in ('completed', 'refunded', 'partial_refunded', 'cancelled')
            row.update(payment=amounts.get('payment', 0), refund=amounts.get('refund', 0),
                       net_settlement=net, held=held, consistent=held >= 0 and (not closed or held == 0),
                       simulation=True)
        return json_response(orders)

    async def flagged_content(self, request):
        await self.page_user(request, staff=True)
        messages = await self.db.all(
            'SELECT m.*,u.nickname,r.name room_name,r.kind room_kind FROM messages m '
            'JOIN users u ON u.id=m.user_id JOIN rooms r ON r.id=m.room_id '
            'WHERE m.moderation IS NOT NULL ORDER BY m.id DESC LIMIT 200')
        posts = await self.db.all(
            'SELECT p.*,u.nickname FROM posts p JOIN users u ON u.id=p.user_id '
            'WHERE p.moderation IS NOT NULL ORDER BY p.id DESC LIMIT 200')
        for item in messages+posts:
            try:
                item['moderation'] = json.loads(item['moderation'])
            except (TypeError, ValueError):
                item['moderation'] = None
        return json_response({'messages': messages, 'posts': posts})
