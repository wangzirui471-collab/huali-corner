# 新 FastAPI 与本机身份/订单兼容入口

已增加 `/api/v1/compat` 的登录、身份、退出和订单接口，由新 API 校验/封套后调用本机旧唯一 writer；没有复制账号或订单数据库。商品等其他领域仍走原入口，整站迁移尚未完成。

完整接手、接口表、三个终端启动和智能客服对接见 [给下一位 AI 的交接](../../docs/refactor/AI-TAKEOVER-AND-INTEGRATION.md)。

要求 Python 3.13 或 3.14、uv 0.13.4。命令均在本目录运行，支持 Windows 中文及空格路径：

```powershell
uv sync --locked
$env:HUALI_ENV = 'local'
# 可选：先启动全新合成数据的旧服务；不配置时兼容接口明确返回 503。
$env:HUALI_LEGACY_ORIGIN = 'http://127.0.0.1:8081'
uv run uvicorn huali.main:app --app-dir src --host 127.0.0.1 --port 8001
```

`GET /health` 与 `/api/v1/health` 证明进程存活。`business_ready=false` 表示整站业务未完成迁移；`compat_enabled` 仅说明依赖已装配。配置缺少 HUALI_ENV 时拒绝启动；兼容源站只允许本机显式 HTTP 端口，生产模式禁止启用。当前不会创建或自动选择业务数据库。

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
