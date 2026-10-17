"""Track synchronous simulated refund attempts without creating a second ledger.

Success is committed with the existing financial transaction. Failed attempts are
recorded only after its rollback. This is not an external payment-provider queue.
"""
import logging
import time

from ..trade.progress import funds_progress

logger = logging.getLogger(__name__)


def migrate_refund_executions(connection) -> None:
    connection.execute('''CREATE TABLE IF NOT EXISTS refund_executions(
        ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),
        order_id INTEGER NOT NULL REFERENCES orders(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),
        amount INTEGER NOT NULL CHECK(amount>0),
        state TEXT NOT NULL CHECK(state IN ('succeeded','failed')),
        attempts INTEGER NOT NULL CHECK(attempts>0),
        attempted_at REAL NOT NULL, executed_at REAL, error_code TEXT)''')


def record_execution(connection, attempt: dict, succeeded: bool) -> None:
    previous = connection.execute('SELECT state,attempts FROM refund_executions WHERE ticket_id=?', (attempt['ticket_id'],)).fetchone()
    # A late failure must never downgrade another successful attempt.
    if previous and previous['state'] == 'succeeded':
        return
    state = 'succeeded' if succeeded else 'failed'
    connection.execute('''INSERT INTO refund_executions
        (ticket_id,order_id,actor_id,amount,state,attempts,attempted_at,executed_at,error_code)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET
        actor_id=excluded.actor_id,amount=excluded.amount,state=excluded.state,
        attempts=excluded.attempts,attempted_at=excluded.attempted_at,
        executed_at=excluded.executed_at,error_code=excluded.error_code''',
        (attempt['ticket_id'], attempt['order_id'], attempt['actor_id'], attempt['amount'], state,
         (previous['attempts'] if previous else 0) + 1, attempt['attempted_at'],
         time.time() if succeeded else None, None if succeeded else 'SIMULATION_EXECUTION_FAILED'))


def record_failed_execution(market, attempt: dict) -> None:
    try:
        with market.tx() as connection:
            record_execution(connection, attempt, False)
            connection.execute('INSERT INTO audit(actor,type,reason,ticket_id,created) VALUES(?,?,?,?,?)',
                               (attempt['actor_id'], 'ticket_refund_failed', '模拟退款执行失败，原事务已回滚；可核对后重试', attempt['ticket_id'], time.time()))
    except Exception:
        # Preserve the original execution error if storage itself is unavailable.
        logger.error('Cannot persist failed simulated refund for ticket %s', attempt['ticket_id'])


def refund_execution(market, ticket: dict) -> dict | None:
    if ticket['type'] != 'refund' or not ticket.get('order_id'):
        return None
    row = market.row('SELECT * FROM refund_executions WHERE ticket_id=?', (ticket['id'],))
    order = market.row('SELECT total,status FROM orders WHERE id=?', (ticket['order_id'],))
    ledger = market.rows('SELECT kind,amount FROM ledger WHERE order_id=?', (ticket['order_id'],))
    balance = funds_progress({**order, 'ledger': ledger})
    legacy = ticket.get('outcome') == 'refund' and ticket['status'] == 'resolved' and any(x['kind'] == 'refund' for x in ledger)
    state = row['state'] if row else 'legacy_recorded' if legacy else 'not_started'
    consistent = None
    if state in ['succeeded', 'legacy_recorded']:
        consistent = balance['consistent'] and (not row or balance['refund_cents'] == row['amount'])
    return dict(state=state, attempts=row['attempts'] if row else 0,
                amount_cents=row['amount'] if row else balance['refund_cents'] if legacy else None,
                attempted_at=row['attempted_at'] if row else None,
                executed_at=row['executed_at'] if row else None,
                error_code=row['error_code'] if row else None, ledger_consistent=consistent,
                approval_status='approved' if ticket.get('outcome') == 'refund' else 'closed_without_refund' if ticket['status'] == 'resolved' else 'pending',
                simulation=True)
