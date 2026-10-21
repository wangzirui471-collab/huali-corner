# 重构实施验证记录

日期：2026-10-21。以下只记录本机已执行的验证；后续每批切片更新本文件。

> 2026-10-22 收尾更新见本文件末尾。完整交付范围、重现命令与接续顺序见 [DELIVERY-HANDOFF.md](./DELIVERY-HANDOFF.md)。早前通过记录与最后一次 Worker 启动失败均保留，不能混同。

## T00 基线

- 起点：`release/2026-10-trial-hotfix@b2b6266`；唯一现有 worktree 为当前目录。开始时只有 `docs/refactor/` 未提交；没有发现适用的 `AGENTS.md`。
- Python 3.12.14、Node 24.21.0。初次执行 `python -B -X utf8 -m unittest discover -s tests -p test_*.py`：462 项，3 failure / 1 error，均在 `test_trial_launcher`；此解释器缺少固定版本 PyMySQL。没有把这些失败归因于重构。
- Node 10 个脚本中，初次有 9 个通过，`user_center.test.mjs` 因 Windows 中文目录 URL 解码错误失败；将夹具改为 `fileURLToPath` 后单独复测通过。
- `test_cloudflare_trade.py` 中新增的 20 件参数预算和 `want_id` 重放用例先失败，修复后本文件 19 项通过。新增请求摘要后又覆盖修改订单、过期预约和未知提交结果路径。`test_checkout_migration.py` 的旧库扩展与新库初始化样例 2 项通过。
- 已安装固定版本 PyMySQL 1.2.3 到项目忽略的 `.local-deps/`。受执行沙箱对新下载文件的读取限制，普通沙箱运行的第二次 464 项仍报告相同依赖失败；在可读取隔离依赖的环境重跑，467 项全部通过（约 148 秒）。之后新增的 `test_checkout_migration.py` 2 项单独通过；完整套件当次发现测试时尚未包含此文件。
- Windows 中文/空格路径下重新运行全部 10 个 Node 脚本：10/10 退出码为 0。
- 旧 `derive` 与 CPython 标准 `hashlib.pbkdf2_hmac` 的合成 600000 轮向量一致，恢复核验的正反例通过（`test_legacy_kdf_vector.py`，1 项）；这不证明 Worker CPU/内存预算。
- 未运行浏览器基准截图、原生微信工具、真实 Cloudflare D1/R2、线上数据盘点。历史发布记录不能替代这些结果。

## 行为合同与改动分类

| 类型 | 范围 | 本轮可执行证据 | 未触及的规则 |
| --- | --- | --- | --- |
| BUG A01 | 1–20 件原子下单守卫参数 | 20 件同卖家成功且守卫单语句绑定参数 ≤100；既有报价与竞态测试 | 真实 D1 参数/FFI 门槛仍需 T01 验证 |
| BUG A02 | 相同请求键的原始请求身份 | 商品、交付、地点、预约、求购编号不同拒绝；原键结果未知与修改订单后重试 | 旧订单无原始摘要时只能走保守旧字段比较 |
| TEST | Windows 中文/空格路径 | `node tests/user_center.test.mjs` 通过 | 真实浏览器与小程序未验 |

交易规则仍以 01 §5–7 和既有 `tests/test_cloudflare_trade.py`、`tests/test_market.py` 等断言为基线。A03 凭据协议、A04 媒体授权、平台恢复上架与会话续期等问题仍需各自独立切片，不能因 A01/A02 修复而视为完成。

## T01 平台探针

`experiments/worker-poc/` 使用隔离配置，D1/R2 均为 `remote:false`，未使用生产 binding ID。锁定的本机工具：uv 0.13.4、Wrangler 4.151.3、workers-py 1.17.8、workers-runtime-sdk 1.9.5、FastAPI 0.157.0；`pywrangler sync` 使用 CPython 3.14.8 和 Pyodide 3.14.2。首次 Worker 冷加载/重载在本机耗时较长，不能当作云端冷启动指标。

本地 Wrangler 实测：`uv run pywrangler d1 execute ... --local --file schema.sql` 成功；启动输出明确显示 DB、MEDIA 和 ASSETS 都为 `local`；`python smoke.py` 最终通过：FastAPI `/api/health`、D1 后续 CHECK 失败时前写入回滚、单 JSON 参数 + 20 行 batch、R2 对象读写、API/媒体 404 JSON、静态页与 SPA 深链、重复本地 Cron 仅保留一条事件。`scheduled(self, controller, env, ctx)` 的 `env` 参数在本地实测为 `None`，使用 `self.env` 后通过。

合成旧 PBKDF2 600000 轮向量在本地 Worker 与 CPython 结果一致；本次暖请求的算法内部计时约 991 ms，`hashlib.pbkdf2_hmac` 在 Worker 中不可用。该耗时是本地 `perf_counter` 墙钟值，不是 Cloudflare CPU 计费结果，也不能据此认定目标套餐可运行。

**仍未通过 T01 的完整退出门槛：** 真实隔离平台上的 D1 并发/100 参数/FFI 行为，8 与 20 件完整业务下单，Pillow/EXIF/WebP 最大合法图片和私密读取授权、真实平台 KDF CPU/内存/冷启动、Cron 延迟/漏跑补偿，以及浏览器 Cookie/CSRF 和静态路由真实平台行为。T02 可继续离线契约、规则和 UI 样板；依赖这些能力的运行位置与发布不得由本地探针替代决定。

## 后续缺陷修复与完整回归

A04 媒体读取已按 [0003](./decisions/0003-resource-media-authorization.md)修复：精确匹配资源引用；在售公开图、历史订单图、未发布图和凭证分别校验；员工须提供已认领且无利益冲突的具体工单；所有动态图片禁止公有缓存。10 个新增媒体用例和 26 个商品用例通过。随后在 Python 3.12.14 + Pillow 12.3.0 + PyMySQL 1.2.3 环境复跑完整旧后端：**480 项全部通过，约 149 秒**。此结果包括早前的请求摘要迁移与旧 KDF 合成向量用例。

## T02 已落地的离线基础

- `apps/api`：唯一组合根、显式环境配置、v1 封套、request_id、字段/业务/HTTP/未知错误边界，OpenAPI 导出；`/health` 与 `/api/v1/health` 明确标记 business_ready=false。
- D1 原子计划：单语句参数/SQL 字节预算、紧邻写操作的 changes() 事务内断言、一次 batch 提交；配套 0002 加法迁移。SQLite 合成测试验证零行 UPDATE 和后续约束失败整体回滚，不代表真实 Worker FFI 已验收。
- `apps/web`：按用户最新确认采用 **JavaScript + Vue 3 + Element Plus**；按钮、输入/表单、提示、标签和弹窗已接入，复用品牌令牌。手写代码无 TypeScript；OpenAPI 生成 `.d.ts` 只供 JSDoc/checkJs 检查与编辑提示，详见 [0004](./decisions/0004-javascript-element-plus.md)。
- HTTP 客户端校验 v1 封套和 DTO，保留 Retry-After、原幂等键与写入结果未知状态；账号/页面上下文切换后取消并拒绝迟到响应。尚未接入身份服务，不能据此声称 Cookie/CSRF 全流程已完成。
- 新方法、测试与任务脚本已补中文注释。Ruff 检查新 Python 方法说明；ESLint 自定义规则检查手写前端具名方法的中文 JSDoc。`scripts/refactor.ps1` 提供 Setup / Check / Contracts / Api / Web 任务。
- 本机 Python 3.13.16 的新 API **17 项测试通过**（HTTP 契约、原子失败注入、依赖边界与图片规则），Ruff check/format 与严格 mypy 通过。前端 **9 项 Vitest 测试、JavaScript/Vue 模板检查、ESLint/Prettier 与默认构建通过**。锁文件入库。当前 Starlette 测试工具对 httpx 有弃用提示，测试仍通过，后续升级测试传输适配时需复核。
- 浏览器实际验证 Element Plus 弹窗打开、Escape 关闭及焦点返回触发按钮。320、390、768、1440 四种目标宽度检查无页面横向溢出，截图保存在本机忽略目录 `artifacts/refactor/`。这只是组件样板证据；旧业务首页截图基线和业务页面视觉迁移仍未完成。
- `.github/workflows/refactor-checks.yml` 已加入新工程、协议漂移与旧业务回归检查，包含 Windows 中文/空格路径；**尚未推送或在 GitHub 执行**。

T02 仍未完成全部退出门槛：正式 Worker 上的新组合根/原子适配器、完整旧新业务 DTO 转换、领域服务、真实隔离 D1/R2 与 T01 剩余平台门槛均需继续验证。当前可运行的是工程与组件预览，不能视为全项目业务重构完成。

## 数据与回滚边界

本轮没有连接或修改任何真实 D1/R2/SQLite/MySQL 数据。`request_hash` 是加法列：全新合成库在 `schema.sql` 中包含；已存在 D1 须先核对 schema，再按 `infra/d1/migrations/0001_add_checkout_request_hash.sql` 应用一次，之后才能部署使用该列的 Worker。此迁移未执行于真实库。旧订单列值为 NULL，仍按旧字段比较重试；旧订单修改后无法重建原始请求，不可声称已解决历史记录的全部重放歧义。代码回滚须保留加法列，不能回滚到不识别新写入语义的交易版本后继续随机写入。

## 2026-10-22 收尾交付

用户要求停止新增任务，完成手头开发并形成交付手册；本批未推进 T03 新业务切片。

### 前端 skill 与表单收尾

- 阅读并使用本机 `ui-ux-pro-max`；第一次通用宣传页推荐不适配，按 skill 收窄重试命中 Marketplace / Directory。保留 04 的品牌和结构，采用清晰输入、可聚焦错误汇总、字段入口、保留输入和明确反馈等适用指导。
- `tdd` 先请求确认测试入口，用户选“优先验证前端界面”。两个页面行为分别先失败再实现：提交失败保留标题并从汇总定位字段；修正后提示通过，继续编辑撤销旧通过结果。通过可见 DOM 和焦点验证，不访问组件内部状态。
- 首次运行新页面测试还发现 public 素材被测试转换器解析成 `file:///brand/...` 的 Windows 路径问题，改为浏览器运行时引用。Element Plus 原生 Node/CJS 互操作使 async-validator 在测试中失效，按 Vitest 的依赖转换能力对库启用 inline；保留真实控件和校验，没有 mock 验证结果。[Vitest 官方配置说明](https://vitest.dev/config/server#deps-inline)
- `scripts/refactor.ps1 -Task Check` 收尾通过：新 API **17 项**、Ruff check/format、严格 mypy；前端 **11 项**、ESLint/Prettier、checkJs/Vue 模板及默认构建通过。
- 浏览器实际验证两字段错误汇总、Tab/Enter 回到字段、修正后的通过提示及保留值。320/390/768/1440 目标宽度均无页面横向溢出。最后修正 Element Plus 表单容器内字段宽度，使手机输入框撑满可用空间；390 宽度下输入实测约 296px，无横向溢出。保存 `form-390.jpg`、`form-1440.jpg` 最终截图，控制台未发现 error 级日志。

### A04 客户端兼容收尾

- Web 通过严格同源 `/media/id` 的 Bearer→Blob 兼容读取解决私密图片不能直接在 img 中带头的问题；换页、换账号取消并使迟到请求失效，URL 由旧路由回收。
- 原生详情通过实际 `app.mediaURL` 下载临时媒体，隐藏/卸载清空内容、删除登记的临时文件；页面或会话变化后清理迟到文件，无权图片显示失败说明。
- `node tests/private_media.test.mjs` 验证授权、第三方路径拒绝、失败响应、账号隔离，以及小程序真实应用/详情代码的认证下载、清理、页面/账号切换和 403 场景。平台边界使用合成 wx 响应；未执行真机。
- 收尾重新运行全部 **11 个** `.test.mjs` / `.test.js` 脚本通过。CI 的发现模式同步覆盖原生 `.test.js`，此前只筛 `.mjs` 会遗漏三项。

### 本地图片探针：成功与最终启动失败分开记录

此前在本地 Worker + Pillow **12.2.0** 已实际运行 `image_smoke.py` 成功：JPEG/PNG/WebP，EXIF 方向与元数据清除，头像缩放，20M 合成像素缩至 1600×1280，5 MiB 填充 JPEG，以及字节/像素超限、截断和动画拒绝；输出可解码，R2 回读一致。首次暖请求观测约 JPEG 331ms、PNG/WebP 10–11ms、头像 56ms、20M 720ms，均为本机墙钟。随后基础 `smoke.py` 通过，KDF 约 982ms。

新 API 仍锁 Pillow **12.3.0**；Worker Emscripten 索引未解析到该版本兼容 wheel。12.3.0 有安全修复，12.2.0 仅用于本地合成探针，不据此开放真实上传。详见 [0005](./decisions/0005-worker-image-runtime.md)。

收尾再次同步白名单源码并复核时，Ruff 报一个导入排序问题，修正后 **5 个探针文件 check/format 通过**。同步触发 Worker 重载，图片首请求随后发生 `ConnectionResetError [WinError 10054]`；运行时输出 `kj/compat/tls.c++:429 ... peer disconnected without gracefully ending TLS session`。停止旧实例后用原隔离配置执行 `uv run --locked pywrangler dev --test-scheduled --port 8787` 重启一次，仍在启动阶段报相同 TLS 断连；此次启动退出码 1。因此**最后一轮图片/基础探针未重新通过**，不能宣称交付时本地 Worker 可稳定启动。没有降低 TLS 校验或改用生产资源绕过。

这个失败不影响已通过的新 API/前端/旧客户端离线检查，但本地 Worker 的最终可重现启动仍是接续门槛。T01 的真实平台验收继续未完成。

最后的输入宽度 CSS 调整后，前端 lint、显式 preview 构建和默认构建再次通过；最终 dist 为默认构建，未开放开发样板。执行 Contracts 重新生成后，OpenAPI 与 `.d.ts` 的 SHA256 均与生成前一致。390/1440 最终截图复制进 `docs/refactor/evidence/` 随手册交付；历史截图仍在忽略的 artifacts 目录。

## GitHub 分支交付更新

2026-10-22，用户在本地交付后明确授权将本批成果提交并更新到 `release/2026-10-trial-hotfix`。提交前核对 GitHub 该分支仍指向实施基线 `b2b62660177f74b596a6add4fc030bd55354d9be`，无需覆盖远端提交。交付文档同步改为分支交付说明；`DELIVERY-FILES.txt` 保留提交前路径快照，M/?? 不代表提交后的当前状态。最新版本通过 Git 与远端分支核对，不将推送等同部署或 CI 已通过。
