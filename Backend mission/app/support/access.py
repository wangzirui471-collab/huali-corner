"""Shared case visibility rules; queue access does not grant private detail access."""


def case_participants(market, ticket):
    participants = {ticket['user_id']}
    if ticket['order_id']:
        order = market.row('SELECT buyer_id,seller_id FROM orders WHERE id=?', (ticket['order_id'],))
        participants.update([order['buyer_id'], order['seller_id']])
    return participants


def case_access(market, user_id, ticket):
    participant = user_id in case_participants(market, ticket)
    role = market.profile(user_id)['role']
    worker = role in ['admin', 'support'] and not participant
    if worker:
        try:
            market.check_conflict(user_id, dict(ticket))
        except Exception as error:
            if getattr(error, 'status', None) != 403:
                raise
            worker = False
    private = worker and (role == 'admin' or ticket['assignee'] == user_id)
    return participant, private, role in ['admin', 'support']


def can_read_order(market, user_id, order):
    if user_id in [order['buyer_id'], order['seller_id']]:
        return True
    role = market.profile(user_id)['role']
    if role == 'admin':
        return True
    return role == 'support' and bool(market.row(
        'SELECT id FROM tickets WHERE order_id=? AND assignee=? AND user_id<>?',
        (order['id'], user_id, user_id)))
