# 新 API 骨架

这是 T02 的隔离工程基础，尚未装配登录、商品和交易业务。现有业务入口按原方式运行。

要求 Python 3.13 或 3.14、uv 0.13.4。命令均在本目录运行，支持 Windows 中文及空格路径：

```powershell
uv sync --locked
$env:HUALI_ENV = 'local'
uv run uvicorn huali.main:app --app-dir src --host 127.0.0.1 --port 8001
```

`GET /health` 与 `/api/v1/health` 证明进程存活。`business_ready=false` 表示业务尚未完成迁移；配置缺少 HUALI_ENV 时拒绝启动。当前不创建、连接或自动选择业务数据库。

检查命令：

```powershell
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv run mypy
$env:PYTHONPATH = 'src'
uv run python -m unittest discover -s tests -p 'test_*.py'
uv run python scripts/export_contract.py
```

唯一装配位置是 `src/huali/bootstrap.py`。`shared` 不依赖 HTTP/Worker/数据库；`transport` 统一处理封套与错误；`infrastructure/d1/atomic.py` 将用例的可信 SQL 计划编译成一个 batch。期望影响行数不符会在事务内触发命名约束错误；使用前必须在隔离目标安装 `infra/d1/migrations/0002_create_atomic_assertions.sql`。当前原子适配器只有合成 SQLite 故障注入证据，Worker FFI、真实 D1 并发与业务接入仍需单独验收。

每个新增方法、测试和任务脚本都必须加中文用途说明；重要参数与结果写清单位和约束。
