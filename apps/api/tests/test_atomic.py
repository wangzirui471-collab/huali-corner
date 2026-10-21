"""用 SQLite 故障注入验证原子计划；实际 Worker FFI 另设平台门槛。"""

import sqlite3
import unittest
from pathlib import Path

from huali.infrastructure.d1.atomic import (
    AtomicPlan,
    AtomicWriter,
    Statement,
    compile_plan,
)
from huali.shared.errors import ApplicationError


class Prepared:
    """测试用 SQL 绑定对象，只记录 SQL 与参数，不连接真实 D1。"""

    def __init__(self, sql: str) -> None:
        """记录可信 SQL，等待绑定参数后在测试 batch 中执行。"""
        self.sql = sql
        self.parameters = ()

    def bind(self, *parameters):
        """保存参数并返回自身，模拟 D1 prepared statement 的链式调用。"""
        self.parameters = parameters
        return self


class SqliteBinding:
    """通过内存 SQLite 的 savepoint 检查 batch 失败时的整体回滚。"""

    def __init__(self, db: sqlite3.Connection) -> None:
        """接收当前用例的独立内存连接，并记录提交次数。"""
        self.db = db
        self.calls = 0

    def prepare(self, sql: str) -> Prepared:
        """创建测试预编译对象，不提前执行 SQL。"""
        return Prepared(sql)

    async def batch(self, statements):
        """按顺序执行完整事务，故障时回滚全部语句并原样抛出异常。"""
        self.calls += 1
        self.db.execute("SAVEPOINT test_atomic")
        try:
            for statement in statements:
                self.db.execute(statement.sql, statement.parameters)
            self.db.execute("RELEASE test_atomic")
        except BaseException:
            self.db.execute("ROLLBACK TO test_atomic")
            self.db.execute("RELEASE test_atomic")
            raise


class AtomicTests(unittest.IsolatedAsyncioTestCase):
    """覆盖零行写入、后续故障、正常提交和单语句预算。"""

    def setUp(self) -> None:
        """初始化合成业务表和正式断言表迁移，不导入旧账号或订单。"""
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        migration = (
            Path(__file__).resolve().parents[3]
            / "infra/d1/migrations/0002_create_atomic_assertions.sql"
        )
        self.db.executescript(migration.read_text(encoding="utf-8"))
        self.db.execute(
            "CREATE TABLE inventory(id INTEGER PRIMARY KEY,version INTEGER)"
        )
        self.db.execute("CREATE TABLE journal(id INTEGER PRIMARY KEY)")
        self.db.execute("INSERT INTO inventory VALUES(1,1)")
        self.binding = SqliteBinding(self.db)
        self.writer = AtomicWriter(self.binding)

    async def test_zero_row_update_rolls_back_previous_write(self) -> None:
        """版本变化导致 UPDATE 零行时，之前的账本写入也必须消失。"""
        plan = AtomicPlan(
            (
                Statement("INSERT INTO journal VALUES(1)", expected_changes=1),
                Statement(
                    "UPDATE inventory SET version=2 WHERE id=1 AND version=9",
                    expected_changes=1,
                ),
            )
        )
        with self.assertRaises(ApplicationError) as raised:
            await self.writer.commit(plan)
        self.assertEqual(raised.exception.code, "VERSION_CONFLICT")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM journal").fetchone()[0], 0
        )
        self.assertEqual(self.binding.calls, 1)

    async def test_late_failure_rolls_back_inventory(self) -> None:
        """业务表后续约束失败时，不能残留已成功的库存更新。"""
        plan = AtomicPlan(
            (
                Statement(
                    "UPDATE inventory SET version=2 WHERE id=1", expected_changes=1
                ),
                Statement("INSERT INTO journal VALUES(1)"),
                Statement("INSERT INTO journal VALUES(1)"),
            )
        )
        with self.assertRaises(sqlite3.IntegrityError):
            await self.writer.commit(plan)
        self.assertEqual(
            self.db.execute("SELECT version FROM inventory").fetchone()[0], 1
        )

    async def test_success_keeps_assertion_table_empty(self) -> None:
        """成功计划只提交一次，断言通过时不遗留技术标记记录。"""
        await self.writer.commit(
            AtomicPlan(
                (
                    Statement(
                        "UPDATE inventory SET version=2 WHERE id=1", expected_changes=1
                    ),
                    Statement("INSERT INTO journal VALUES(1)", expected_changes=1),
                )
            )
        )
        self.assertEqual(
            self.db.execute("SELECT version FROM inventory").fetchone()[0], 2
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM refactor_atomic_assertions"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(self.binding.calls, 1)

    def test_invalid_plan_budget_is_rejected_before_submit(self) -> None:
        """空计划、超预算 SQL 或非法影响行数在触及数据库前被拒绝。"""
        for plan in (
            AtomicPlan(()),
            AtomicPlan((Statement("SELECT ?", tuple(range(101))),)),
            AtomicPlan((Statement("SELECT 1" + " " * 100_000),)),
            AtomicPlan(
                (Statement("UPDATE inventory SET version=2", expected_changes=True),)
            ),
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                compile_plan(plan)
        self.assertEqual(self.binding.calls, 0)


if __name__ == "__main__":
    unittest.main()
