"""D1 异步数据访问层。

为什么必须新建这一层
--------------------
现有 `core/database.py` 是同步的：`with store.tx() as c: c.execute(...)`，依赖
`sqlite3` 的连接对象、`BEGIN IMMEDIATE` 事务和 `threading.RLock` 写锁。

在 Python Workers 里实测：
  · `threading.Thread.start()` 抛 RuntimeError —— 没有线程；
  · `sqlite3` 能 import，但那是无持久化的内存桩；
  · `time.sleep()` 会阻塞单线程事件循环。

所以旧的事务模型无法成立，D1 的每一次访问都必须是 await。

事务语义（重要，别在这里加"假事务"）
------------------------------------
D1 **没有**交互式事务：不能 `BEGIN` 之后读一个值、在 Python 里判断、再决定下一步。
D1 唯一的事务原语是 `batch()`：一批语句在同一个事务里执行，要么全成功要么全回滚。

因此订单、库存、退款、账本这类需要原子性的写操作，必须：

  1. 把"判断"写进 SQL 的 WHERE 里，而不是写在 Python 的 if 里；
  2. 用 `batch()` 一次性提交，保证全成或全不成；
  3. 用每条的 `changes` 判断守卫是否命中，未命中就整体判定失败。

反例（不要这样写）：
    stock = await db.first('SELECT stock FROM products WHERE id=?', (pid,))
    if stock and stock['stock'] > 0:          # 读到的是快照，判完可能已被抢走
        await db.run('UPDATE products SET stock=stock-1 WHERE id=?', (pid,))

正例：
    results = await db.batch([
        ('UPDATE products SET stock=stock-1 WHERE id=? AND status=? AND stock>0',
         (pid, 'available')),
        ('INSERT INTO ledger(order_id,kind,amount,created) VALUES(?,?,?,?)',
         (oid, 'charge', amount, now)),
    ])
    db.expect(results[0], '商品已下架或库存不足')
    db.expect(results[1], '账本写入失败')

多次独立请求拼接成的"事务"不算事务，不要用。
"""
from ..core.errors import DomainError

__all__ = ['Database']


def _as_dict(row):
    """D1 返回的对象支持下标访问，但统一转成 dict，便于现有 service 的 row['x'] 写法。"""
    return dict(row) if row is not None else None


class Database:
    """包一层 D1 绑定，暴露最小、够用的异步接口。"""

    def __init__(self, binding):
        if binding is None:
            raise RuntimeError('D1 binding DB is missing')
        self._db = binding

    # ---- 读 ----------------------------------------------------------------

    async def all(self, sql, params=()):
        result = await self._db.prepare(sql).bind(*params).all()
        return [_as_dict(row) for row in (result.results or [])]

    async def first(self, sql, params=()):
        result = await self._db.prepare(sql).bind(*params).first()
        return _as_dict(result)

    async def scalar(self, sql, params=()):
        row = await self.first(sql, params)
        if not row:
            return None
        return next(iter(row.values()))

    # ---- 写 ----------------------------------------------------------------

    async def run(self, sql, params=()):
        """单条写。返回 meta，调用方必须用 expect() 检查 changes。

        单条写是原子的，但**不构成业务事务**：需要多步一致时用 batch()。
        """
        return await self._db.prepare(sql).bind(*params).run()

    async def insert(self, sql, params=()):
        """插入并返回新行 id。依赖 RETURNING，D1 支持。"""
        row = await self.first(sql, params)
        if not row:
            raise DomainError('写入未返回结果', 409)
        return next(iter(row.values()))

    # ---- 事务 --------------------------------------------------------------

    async def batch(self, statements):
        """在同一个 D1 事务里执行一批语句。

        statements: [(sql, params), ...]
        返回每条语句的 meta 列表。任一条失败，整批回滚。
        """
        prepared = [self._db.prepare(sql).bind(*params) for sql, params in statements]
        if not prepared:
            return []
        return list(await self._db.batch(prepared))

    @staticmethod
    def expect(meta, message='操作未生效'):
        """断言一条语句确实影响了行。守卫条件没命中时 changes 为 0。"""
        changes = 0
        if meta is not None:
            changes = meta.get('changes', 0) if hasattr(meta, 'get') else getattr(meta, 'changes', 0)
        if not changes:
            raise DomainError(message, 409)
        return changes
