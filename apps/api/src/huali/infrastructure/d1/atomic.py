"""将可信应用用例的写入计划编译成一次 D1 batch。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, Self

from huali.shared.errors import ApplicationError

SqlValue = str | int | float | bytes | None
MAX_BOUND_PARAMETERS = 100
MAX_SQL_BYTES = 100_000


@dataclass(frozen=True)
class Statement:
    """内部可信 SQL；参数只能绑定值，expected_changes 用于事务内断言。"""

    sql: str
    parameters: tuple[SqlValue, ...] = ()
    expected_changes: int | None = None


@dataclass(frozen=True)
class AtomicPlan:
    """一个用例需同时提交的有序语句；不允许仓储各自提交半个用例。"""

    statements: tuple[Statement, ...]
    conflict_message: str = "状态已变化，请重新确认"


class PreparedStatement(Protocol):
    """限定 Worker FFI 所需接口，避免 JS 动态类型扩散到业务层。"""

    def bind(self, *parameters: SqlValue) -> Self:
        """绑定 SQL 值并返回预编译语句，供同一 batch 执行。"""
        ...


class D1Binding(Protocol):
    """仅暴露 prepare 与 batch，不向业务层提供独立提交能力。"""

    def prepare(self, sql: str) -> PreparedStatement:
        """从可信 SQL 创建语句；不接受终端用户提供 SQL。"""
        ...

    async def batch(self, statements: Sequence[PreparedStatement]) -> object:
        """在单一 D1 事务内执行全部语句，任一失败则回滚。"""
        ...


def compile_plan(plan: AtomicPlan) -> tuple[Statement, ...]:
    """检查参数和 SQL 字节预算，并紧跟写操作插入 changes() 断言。

    断言在事务内主动触发约束错误，因此零行 UPDATE 会回滚此前所有写入。
    使用前必须安装 0002 迁移；不能提交成功后才根据返回值假装回滚。
    """
    if not plan.statements:
        raise ValueError("原子计划不能为空")
    compiled: list[Statement] = []
    for statement in plan.statements:
        if len(statement.parameters) > MAX_BOUND_PARAMETERS:
            raise ValueError("SQL 绑定参数超过 100 个，请使用有界集合或 JSON 参数")
        if len(statement.sql.encode("utf-8")) > MAX_SQL_BYTES:
            raise ValueError("SQL 文本超过单语句预算")
        if not statement.sql.strip():
            raise ValueError("SQL 不能为空")
        compiled.append(statement)
        expected = statement.expected_changes
        if expected is not None:
            if type(expected) is not int or expected < 0:
                raise ValueError("预期影响行数必须为非负整数")
            compiled.append(
                Statement(
                    "INSERT INTO refactor_atomic_assertions(assertion_key,ok) "
                    "SELECT 'changes',0 WHERE changes()<>?",
                    (expected,),
                )
            )
    return tuple(compiled)


class AtomicWriter:
    """负责单次原子提交；用例创建计划，适配器执行及翻译约束失败。"""

    def __init__(self, binding: D1Binding) -> None:
        """注入当前请求的 D1 binding，不读取全局 env 或连接其他数据库。"""
        self.binding = binding

    async def commit(self, plan: AtomicPlan) -> None:
        """只发起一个 batch；约束断言失败变为冲突，其他故障保留未知结果。"""
        statements = compile_plan(plan)
        prepared = [
            self.binding.prepare(item.sql).bind(*item.parameters) for item in statements
        ]
        try:
            await self.binding.batch(prepared)
        except Exception as error:
            if "huali_atomic_assertion" in str(error):
                raise ApplicationError(
                    "VERSION_CONFLICT", plan.conflict_message
                ) from None
            # 网络或 FFI 异常可能发生在提交之后，调用方须按原幂等键恢复。
            raise
