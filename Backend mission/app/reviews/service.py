"""评价模块：完成订单后的双方互评与好评加分。

拆分说明（开发规范 §3.1）：评价原先挂在 ``SupportService`` 上，导致
「订单评价」与工单、信誉处置耦合——改评价规则会牵动客服模块。现独立为
``ReviewService``，方法名、参数、返回结构与 ``/api/review`` 合同保持不变，
数据库 schema 与事务边界也不变。
"""
import time

from ..account.credit import (
    AWARD_DAILY_CAP,
    AWARD_MONTHLY_CAP,
    AWARD_PER_REVIEW,
    AWARD_REASON_PREFIX,
    GOOD_REVIEW,
    day_start,
    month_start,
)
from ..core.errors import ValidationMixin


class ReviewService(ValidationMixin):
    """订单评价：写入评价，并按规则给被评价方加信誉分。"""

    def review(self, u: int, oid: int, rating: int, body: str) -> dict:
        """写入或更新一条订单评价。

        只允许已完成的有效订单双方评价；同一订单同一用户重复提交时按
        ``(order_id, user_id)`` 覆盖，不产生重复记录。
        """
        order = self.order(u, oid)
        self.require(
            order['status'] == 'completed' and u in [order['buyer_id'], order['seller_id']],
            '完成真实有效订单后才能评价',
        )
        self.require(type(rating) is int and 1 <= rating <= 5, '评分需1至5分')
        with self.tx() as c:
            existing = c.execute(
                'SELECT rating FROM reviews WHERE order_id=? AND user_id=?', (oid, u)
            ).fetchone()
            c.execute(
                'INSERT INTO reviews(order_id,user_id,rating,body,created) VALUES(?,?,?,?,?)'
                ' ON CONFLICT(order_id,user_id) DO UPDATE'
                ' SET rating=excluded.rating,body=excluded.body',
                (oid, u, rating, self.text(body, 500, '评价'), time.time()),
            )
            # 好评成交自动加分（方案 A）：4–5 星给「被评价方」+1。
            # 只有「从没评过」或「从差评改成好评」时加——重复好评、好评改好评
            # 都不重复加；好评改差评不回扣（已发的分不追回，规则从简）。
            if rating >= GOOD_REVIEW and (not existing or existing['rating'] < GOOD_REVIEW):
                ratee = order['seller_id'] if u == order['buyer_id'] else order['buyer_id']
                self._award_good_review(c, ratee, oid, rating)
        return {'ok': True, 'simulation': True}

    def _award_good_review(self, c, target: int, oid: int, rating: int) -> None:
        """好评加分的落库：查日／月上限 → 加分 → 写审计（actor=0 表示系统）→ 通知。

        上限只统计「自动好评加分」（用 reason 前缀区分），不把管理员手工加分
        算进来——申诉成功那种 +分 不该占用好评的名额。
        """
        now = time.time()
        day = day_start(now)
        month = month_start(now)
        daily = c.execute(
            "SELECT COUNT(*) n FROM audit WHERE target=? AND type='credit' AND delta>0"
            " AND reason LIKE ? AND created>=?",
            (target, AWARD_REASON_PREFIX + '%', day),
        ).fetchone()['n']
        if daily >= AWARD_DAILY_CAP:
            return
        monthly = c.execute(
            "SELECT COUNT(*) n FROM audit WHERE target=? AND type='credit' AND delta>0"
            " AND reason LIKE ? AND created>=?",
            (target, AWARD_REASON_PREFIX + '%', month),
        ).fetchone()['n']
        if monthly >= AWARD_MONTHLY_CAP:
            return
        reason = f'{AWARD_REASON_PREFIX}（订单 #{oid} · {rating} 星）'
        c.execute(
            'UPDATE users SET score=MIN(100,score+?) WHERE id=?',
            (AWARD_PER_REVIEW, target),
        )
        c.execute(
            "INSERT INTO audit(actor,target,type,delta,reason,created) VALUES(?,?,?,?,?,?)",
            (0, target, 'credit', AWARD_PER_REVIEW, reason, now),
        )
        self.notify(
            c,
            target,
            'credit',
            f'你因订单 #{oid} 获得好评，信誉分 +{AWARD_PER_REVIEW}。',
        )
