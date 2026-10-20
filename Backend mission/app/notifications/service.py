"""通知模块：站内通知的写入、读取与已读标记。

通知由各领域在业务事务内通过 ``self.notify(...)`` 写入，复用调用方传入的
数据库连接，保证通知与业务状态同事务提交（开发规范 §4.4）。

拆分说明（规范 §3.1）：本模块只搬运既有实现，方法名、参数与返回结构保持
不变；``/api/notifications``、``/api/badges`` 等接口合同不受影响。
"""
import time

from ..core.errors import ValidationMixin


class NotificationService(ValidationMixin):
    """站内通知的领域服务。"""

    def notify(
        self,
        c,
        user_id: int,
        kind: str,
        body: str,
        order_id: int | None = None,
        ticket_id: int | None = None,
        post_id: int | None = None,
        product_id: int | None = None,
    ) -> None:
        """在调用方事务内写入一条通知。

        复用调用方连接 ``c``，通知与业务状态同事务提交。
        ``order_id`` / ``ticket_id`` / ``post_id`` / ``product_id`` 互斥，
        由前端按有值的字段决定跳转目标。
        """
        c.execute(
            'INSERT INTO notifications'
            '(user_id,kind,order_id,ticket_id,post_id,body,created,product_id)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (user_id, kind, order_id, ticket_id, post_id, body, time.time(), product_id),
        )

    def notifications(self, u: int, limit: int = 100) -> dict:
        """返回指定用户的站内通知列表与未读数。"""
        rows = self.rows(
            'SELECT id,kind,order_id,ticket_id,post_id,product_id,body,read_at,created'
            ' FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?',
            (u, int(limit)),
        )
        unread = self.row(
            'SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read_at IS NULL',
            (u,),
        )['n']
        return {'unread': unread, 'items': rows}

    def read_notifications(self, u: int, nid: int | None = None) -> dict:
        """把单条（``nid``）或该用户全部未读通知标记为已读。"""
        with self.tx() as c:
            if nid:
                c.execute(
                    'UPDATE notifications SET read_at=? WHERE id=? AND user_id=?',
                    (time.time(), int(nid), u),
                )
            else:
                c.execute(
                    'UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',
                    (time.time(), u),
                )
        return {'ok': True}

    def badges(self, u: int) -> dict:
        """顶栏角标的一次性数据源：通知未读 + 聊天未读。

        前端每次路由切换都会拉一次，所以这里必须是两个 COUNT，
        不能把通知列表和会话列表整个捞出来。
        """
        return {
            'notifications': self.notifications(u, 1)['unread'],
            'chat': self.chat_unread(u),
        }
