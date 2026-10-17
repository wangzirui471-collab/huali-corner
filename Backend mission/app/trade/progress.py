"""Read-only projections of existing order, delivery, case and ledger records."""
from collections import defaultdict


def funds_progress(order: dict) -> dict:
    amounts = defaultdict(int)
    kinds = set()
    for entry in order.get('ledger', []):
        amounts[entry['kind']] += entry['amount']
        kinds.add(entry['kind'])
    payment = amounts['payment']
    refund = amounts['refund']
    settled = amounts['settlement'] - amounts['settlement_reversal']
    held = payment - refund - settled
    consistent = (all(value >= 0 for value in amounts.values())
                  and ('payment' not in kinds or payment == order['total'])
                  and 0 <= refund <= payment and 0 <= settled <= payment
                  and amounts['settlement_reversal'] <= amounts['settlement'] and held >= 0
                  and (order['status'] not in ['completed', 'refunded', 'cancelled'] or held == 0))
    if not consistent:
        state, label = 'needs_review', '流水异常，需管理员核对'
    elif 'refund' in kinds:
        state, label = ('refunded', '已模拟全额退款') if refund == payment else ('partially_refunded', '已模拟部分退款')
    elif 'payment' not in kinds:
        state, label = 'not_paid', '尚未模拟付款'
    elif order['status'] == 'disputed':
        state, label = 'on_hold', '售后处理中，暂停自动结算'
    elif 'settlement' in kinds:
        state, label = 'settled', '已模拟结算'
    else:
        state, label = 'held', '已模拟付款，等待交付与收货'
    return dict(state=state, label=label, payment_cents=payment, refund_cents=refund,
                net_settlement_cents=settled, held_cents=held, consistent=consistent,
                next_actor='admin' if not consistent else None, simulation=True)


def order_progress(order: dict, refund_tickets: list[dict]) -> dict:
    status = order['status']
    labels = {'awaiting_payment': '待买家付款', 'paid': '待卖家交付',
              'awaiting_handover': '待买家核对交接', 'awaiting_receipt': '待买家确认收货',
              'completed': '订单已完成', 'cancelled': '订单已取消',
              'disputed': '订单售后处理中', 'refunded': '订单已退款结案'}
    actor = {'awaiting_payment': 'buyer', 'paid': 'seller', 'awaiting_handover': 'buyer',
             'awaiting_receipt': 'buyer', 'disputed': 'staff'}.get(status)
    if order.get('completed_at'):
        delivery, label = 'received', '买家已确认收货'
    elif order.get('handover_at'):
        delivery, label = 'handed_over', '买家已核对实物交接'
    elif order.get('delivered_at'):
        delivery, label = 'seller_marked', '卖家标记已交付，待买家核对'
    elif status in ['cancelled', 'refunded']:
        delivery, label = 'not_delivered', '未记录实物交付'
    elif status == 'awaiting_payment':
        delivery, label = 'not_started', '付款后安排交付'
    else:
        delivery = 'scheduled' if order.get('schedule_confirmed') else 'awaiting_schedule'
        label = '卖家已确认交付时间' if order.get('schedule_confirmed') else '等待卖家确认交付时间'
    countdown = order['handover_at'] + 86400 if status == 'awaiting_receipt' and order.get('handover_at') else None
    active = next((ticket for ticket in refund_tickets if ticket['status'] not in ['resolved', 'rejected']), None)
    latest = active or next(iter(refund_tickets), None)
    after = dict(state='none', label='暂无售后申请', ticket_id=None, next_actor=None)
    if latest:
        case_labels = {'open': '等待客服受理', 'processing': '客服处理中', 'review': '待管理员复核',
                       'resolved': '售后已结案', 'rejected': '售后未获支持'}
        after = dict(state=latest['status'], label=case_labels.get(latest['status'], '售后进度待核实'),
                     ticket_id=latest['id'], next_actor='staff' if active else None)
    elif status == 'disputed':
        after.update(state='unknown', label='售后记录待核实', next_actor='staff')
    return dict(order=dict(state=status, label=labels.get(status, '订单进度待核实'), next_actor=actor),
                delivery=dict(state=delivery, label=label,
                              next_actor='buyer' if delivery in ['seller_marked', 'handed_over'] and actor == 'buyer' else 'seller' if actor == 'seller' else None,
                              method=order['delivery'], auto_receipt_at=countdown),
                after_sales=after, funds=funds_progress(order), simulation=True)
