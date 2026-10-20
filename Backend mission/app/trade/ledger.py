"""交易账本：模拟资金流水的写入与重算。

账本只记录「发生过的钱」，不负责订单状态；订单状态机在 ``trade/orders.py``。
拆分后改计费／冲销规则不必触碰订单流程，改订单流程也不会误改账本。
"""
import time


class LedgerService:
    """模拟账本：流水写入与撮合服务费重算。"""

    def journal(self, c, oid: int, kind: str, amount: int) -> None:
        """幂等写入一条账本流水（同一订单同类流水只记一次）。"""
        c.execute(
            'INSERT OR IGNORE INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',
            (oid, kind, amount, time.time()),
        )

    def recalc_service_fee(self, c, oid: int, subtotal: int) -> None:
        """订单改单后按新小计重算 5% 撮合服务费。

        只在订单已有 ``service_fee`` 流水时更新；没有则不凭空补记，
        与拆分前行为一致。
        """
        row = c.execute(
            "SELECT amount FROM ledger WHERE order_id=? AND kind='service_fee'",
            (oid,),
        ).fetchone()
        new_fee = subtotal * 5 // 100
        if row and row['amount'] != new_fee:
            c.execute(
                'UPDATE ledger SET amount=? WHERE order_id=? AND kind=?',
                (new_fee, oid, 'service_fee'),
            )
