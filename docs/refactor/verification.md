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


## 2026-10-22 换机接手环境复现切片

以下是换机接手后实际执行记录，与上文原交付电脑的结果分开保存。

- 从 GitHub 拉取并核对分支 `release/2026-10-trial-hotfix@e611c31084aae51f46b5fe94ff1802d0736eb50b`；新目录 `C:\Users\7M\Desktop\前端\huali-corner-refactor` 初始干净。旁边原 `huali-corner-trial` 为另一分支并有用户修改，未覆盖。失败的首次克隆残留只移到忽略目录保存，没有 reset/clean。
- 找到本机 Conda Python **3.13.12**（`D:\developTools\python.exe`）。新 API 与 PoC 宿主依赖分别装在项目虚拟环境；全局 Python 未安装业务依赖。应用自带 Python **3.12.14** 另用于旧回归。本机 PATH Node 是 **18.20.4**，检查实际使用应用自带 **24.19.0**。
- 用户明确选择继续项目独立环境，不装系统组件。Docker 未找到；WSL 未安装。没有安装 Docker、WSL 或全局替换 Python/Node。
- Windows autocrlf 导致初检 Prettier 29 文件失败；只恢复 apps/web 的 LF 后，基线 **11 项**、lint/typecheck/build 通过；新增 `.gitattributes` 固定新前端 LF。部分已跟踪文件 Git 状态仍显示 M，但 `git diff` 无内容差异，未用重置/暂存消掉标记。
- 新 API：**17 项通过**；Ruff check/format（20 文件）和严格 mypy（16 文件）通过。重新导出 OpenAPI 无内容漂移；生成声明只发生 CRLF/LF 差异，Git blob 与 HEAD 一致。
- 旧客户端全部 **11 个脚本通过**。旧后端完整回归第一次在受限环境有 1 failure + 1 error：旧启动器扫描 `C:\Users\7M\AppData\Local\Programs\Python` 被拒绝；同一项目环境在授权执行后 **482 项通过，185.799 秒**。日志保存于忽略目录 `artifacts/refactor/legacy-{sandbox,full}.log`。482 包括当时新增的两个任务入口用例；之后新增第三个环境恢复用例，仅单独运行该文件 3 项通过，未声称整套 483 项重跑。
- `refactor.ps1 -Task Setup -PythonExecutable` 可显式选已有解释器，路径错误先停止；uv 禁止自动下载 Python，项目缓存变量在任务结束后恢复。三个任务脚本测试验证中文/空格路径、缺失解释器前置失败和环境恢复，先观察失败后修正通过。
- Worker：锁定 SDK 选择 CPython 3.14/Pyodide 3.14.2，原全局 uv 0.11.32 不满足 SDK>=0.12.3；单独把 uv 0.13.4 和构建解释器放到项目忽略目录。Pyodide 大包下载中用户调整为前端先行，已停止下载，没有完成 Worker 启动或复现/解决 TLS 断连；不能把依赖准备写成平台通过。
- 官方图片索引访问与 wheel 解析仍未成功确认维护中的正式路线；正式 API 保持 Pillow 12.3.0，PoC 12.2.0 仅合成验证。安全后续见决策 0005。
- GitHub Actions REST 查询遭共享 IP 限流，未确认最新 CI 结果。未连接真实 D1/R2/MySQL，未部署、迁移或提交/推送。

## 2026-10-23 T03–T07 前端候选

用户授权调整顺序：先完成 T03–T07 的前端代码，浏览器和真实业务联调交另一台电脑。范围/启动/待验收见 [FRONTEND-TRIAL-HANDOFF.md](./FRONTEND-TRIAL-HANDOFF.md)。

### 已实现与本机实际检查

- 新增身份、商品、清单订单、工单、社区论坛/求购/好友消息、分权工作台页面；通过既有 `/api/*` 唯一 writer 读写。新 API 仍 `business_ready=false`，未新增业务后端或修改原生小程序。
- 本机使用 Node 24.19.0。最终 `vue-tsc --noEmit -p jsconfig.json`、`eslint . --max-warnings 0`、`prettier --check .` 全部退出码 0；Vitest **13 个文件、29 项通过，10.93 秒**。随后同批默认构建与 trial 构建均退出码 0，输出分别为 `dist` 和 `dist-trial`，没有大于 500 kB 的 chunk 警告。检查使用项目内工具和显式 Node 路径，没有替换全局 Node。
- 核心规则先失败后实现：旧协议无封套/5xx 未知写结果/账号迟到拒绝；精确金额、checkout 原键/异内容保护、订单归属；旧链接与回环代理拒绝；资料版本冲突；启动竞态取消；页面卸载后禁止后续上传；错误反馈聚焦；首页返回保留快照；下载 JSON 正文迟到时，旧 401 不清新账号（新增用例先失败，再补取消/身份复核通过）。页面合成检查另验证消息原键恢复、favorited 取消、查档不预取和缺三视图不写入。
- 页面请求绑定身份与生命周期，文件读取或 KDF 结束后的后续请求也受原页面取消控制。恢复码独立留在会话内存，避免登录/改密时重挂载丢失；不写入存储。
- 默认构建关闭业务入口；trial 构建单独输出 `dist-trial`，按页面拆 chunk。预览和开发代理只允许本机 HTTP 后端；保留原 Host/Origin 对应关系。

### 尚未执行与已知限制

本轮未启动业务浏览器验收、未实际登录/发布图片/交易/退款/聊天/处置账号/生成备份，未提供新增业务页面截图。另一台电脑需要依清单测试合成旧库和浏览器，不能用 mock 页面测试、构建或旧截图替代。

聊天沿用旧最近 200 条替换式轮询及已读位点，没有新增增量变更游标或完整历史分页；其他列表沿用旧后端上限，性能/N+1 仍待后端切片解决。外站示例图片显示占位，认证头不会发往外站。

T00–T02 剩余门槛、Worker TLS、正式图片路线、新后端迁移、真实平台事务/KDF/图片预算、Cron、Cookie/CSRF、微信真机、数据恢复和 T08/T09 均未因此完成。本轮改动未提交或推送，CI 未执行本轮代码。

### 最终任务入口复核

2026-10-23 单独重跑 `test_refactor_tasks.py`：默认沙箱 TEMP 允许建立顶层临时目录、拒绝创建其 `scripts` 子目录，三个用例均未进入被测任务，随后临时目录清理也报拒绝访问，合计 6 个 error。没有改业务代码或放宽检查；仅在本次进程把 TEMP/TMP 指到项目忽略目录 `artifacts/refactor/task-temp`，结束后恢复原值，**3 项通过，2.406 秒**。未重跑整套旧后端回归；不能把本次环境错误隐藏或称为业务断言失败。

### 换机增量包核对

已生成忽略目录 `artifacts/refactor/huali-frontend-trial-20261023.zip`，基于 e611c31084aae51f46b5fe94ff1802d0736eb50b：56 项修改/新增源码、文档与测试，42 项 trial 构建文件，加基线/范围/说明/摘要清单共 102 个 ZIP 条目。重新读取归档检查 CRC、每项字节与 `MANIFEST.sha256` 均通过；包外 `.zip.sha256` 用于传输核对。文档更新后重新生成并核对最终包。它是增量覆盖包，须合入基线的全新干净副本；不含依赖环境、数据库或用户媒体。包没有提交到 Git，也未部署。

## 2026-10-23 用户确认首页方案后的应用记录

### 范围与授权

先独立预览，再经用户“没什么问题，继续吧”授权应用。变更：首页、商品卡片、共享 SVG 图标、页头和五槽导航、限定同源示例图显示。后端和原生小程序未变，未连接真实数据。

### 实际结果

- 新增 9 个正式前端行为用例；首轮已有 6 个断言失败，分别暴露缺少轮播暂停、追加错误隐藏旧列表、卡片收藏缺失和固定示例图缺失。完成后增加跨筛选收藏缓存用例，先观察旧快照未失效的失败再修复。
- 最终 Vitest **14 个文件、38 项通过，7.72 秒**。`vue-tsc --noEmit -p jsconfig.json`、`eslint . --max-warnings 0`、`prettier --check .` 全部退出码 0。默认构建 **477ms**、trial 构建 **524ms**，均成功，无大 chunk 警告。
- 独立评审宿主改用实际 MarketLayout/HomePage/ProductCard + 合成 fetch，先替换 fetch 再动态导入业务模块，未知接口拒绝，绝不转发真实请求。宿主一次缺少 vue-router 显式路径导致构建失败，仅修复宿主 alias 后成功；不归因于业务构建。
- 浏览器实际验证：搜索“台灯”返回 1 件，清除后恢复 9 件；独立收藏的 aria-pressed=true，收藏页出现 2 件；取消对应收藏后，最终收藏页剩 1 件；这些写入只改变合成内存。
- 手机初检发现旧 `.campus` 样式误隐藏第二专题、原字符图标未替换及原生按钮边框，改为独立专题名称和完整作用域规则后复核。最终 320/390/768/1440 均无整页横向溢出，两窗均可见，商品列数 2/2/3/4；所有六个轮播控制实际宽 44px。
- 最终浏览器 warn/error 记录为空，保存 `evidence/home-applied-{1440,390}.png`。截图来自合成宿主，不能当作真实旧库、Worker 或微信真机验收。
- 扫描最终 `apps/web/dist` 与 `dist-trial` 的 JS，均不包含 `installPreviewApi`、`ui-preview-synthetic-only`、评审说明条或 preview.invalid 合成源。正式业务仍调用旧 `/api/*` 唯一 writer。
- 旧 29 项 ZIP 已保存独立副本；当前同名 ZIP 随代码/手册/新截图重新生成：68 项源码/文档/测试与证据、46 项 trial 产物，连同基线/范围/说明/摘要清单共 118 条；CRC、逐项字节和逐文件 SHA256 已通过，文档定稿后再次生成并核对。未提交、推送、部署；未重跑无关的后端全量回归。

发布/订单/聊天的其他 UX 建议不在本次首页切片中。真实联调仍须另一台电脑执行。

## 2026-10-23 业务页面预览入口补全

用户反馈 5198 的社区、论坛、消息和订单均进入占位页。原因是评审宿主 main.js 自建路由仅挂首页/收藏；并非正式 apps/web 路由缺少这些页面。

- 删除评审宿主自建的两页路由与 catch-all 占位，改为动态导入正式 app/router.js，并以 trial 模式构建宿主。合成 fetch 仍在业务模块导入前安装，未知资源不转发真实服务。
- 增补合成帖子/评论/求购、会话/消息/通知/好友、买卖订单/报价、工单/回复、个人资料和自有商品，保持旧 DTO 的对象/数组形态与数字 ID。学院配置改为组件实际消费的对象列表；演示 SVG 从旧客户端原素材复制到本机预览资源目录。
- 新增 2 个预览边界测试，先看到 /posts 返回 501 和写入返回 501 的失败，再修复。预览目录最终 **2 文件、5 项通过，12.98 秒**，其中 3 项为此前首页独立稿用例。最后 trial 宿主构建 **558ms** 成功。
- 浏览器通过实际导航验证社区 4 帖、论坛 2 帖、订单 3 条、消息会话列表和 3 条私聊正文、售后 2 工单；另实际打开个人中心、自有商品、求购 2 条和发布页 4 个文件槽。最终 warn/error 记录为空。
- 普通演示账号只具 user 权限，保留工作台角色门禁。除原有仅内存收藏演示外，所有业务写请求返回明确的 403 预览提示，不假报发送/下单成功；单测验证不会调用上游 fetch。没有登录真实账号、发送消息、发布商品或执行交易。
- 保存 `evidence/pages-preview-community.png`，刷新两个已有预览标签。当前 5198 展示正式组件和演示数据；4173 的 trial + 隔离旧服务才是另一电脑真实业务联调入口。
- 本次未修改 apps/web 业务源码/构建或后端；38 项正式前端结果沿用上一节，不声称本次重跑。只更新本机评审宿主、交付/验证说明和截图，并重新核对增量包。

## 2026-10-24 社区、论坛、消息、订单的布局评审稿

本轮仅修改 artifacts 中的独立预览及交付记录。正式前端 38 项为上轮证据，没有在本轮重跑；未改后端、真实数据或生产运行配置。

实际执行：

- 新增社区按需展开/收起保留草稿、订单状态直接筛选两项交互测试；先对旧界面运行，分别因缺少展开入口和状态按钮失败，再修改评审副本。另补预览拒绝发布时保留标题/正文与持久错误的回归用例。
- 首轮完整运行遇到 Element Plus 等模块冷加载超过 10 秒的 beforeAll 超时；测试初始化允许 30 秒后重跑。未改变业务请求超时或安全策略。
- 独立候选类型检查曾发现模板内嵌订单计数表达式的 session 解包错误，移入有中文 JSDoc 的 countOrders 后，通过 `vue-tsc --noEmit -p artifacts/refactor/ui-preview/jsconfig.review.json`。
- 最终 `vitest run --config vite.config.js`：**3 文件、8 项通过，5.88 秒**，包括原有首页预览与合成接口边界用例。
- 改动范围的 Prettier 检查通过；最终 `vite build --mode trial --config vite.config.js`：**524ms 成功**。以上配置均指独立 ui-preview 宿主，没有重新构建正式 dist/dist-trial。
- 本机回环预览重新启动于 **http://127.0.0.1:5198/**。顶部提供社区、论坛、消息、订单切换入口。
- 浏览器工具获取 localhost 标签时被访问策略拒绝，未通过其他浏览器或截图方式绕过。**本轮没有新截图，没有 320/390/768/1440 实际视觉验收，也没有真实后端联调结论。** CSS 含响应式规则不等于已验收。

设计确认待用户；正式业务组件、已批准首页和上一版换机包保持本轮编辑前状态。未执行提交、推送、部署、真实发送或交易。

### 同日补记：恢复 5198 本机连接

- 用户提供 `/messages/9` 的 `ERR_CONNECTION_TIMED_OUT` 截图。隔离命令环境探测先返回 WinError 10013；获准的隔离环境外只读探测确认五个页面均超时，不据此修改电脑防火墙或代理。
- 首次后台启动因 5198 已被占用而失败。检查端口与命令行，确认占用者为本项目 Vite preview；只停止该已核实进程，并在隔离环境外重新隐藏启动，仍只监听 127.0.0.1:5198。
- 随后直接请求 `/`、`/community`、`/forum`、`/orders`、`/messages/9`，**五项均返回 HTTP 200**；HTML 引用的 **6 个入口脚本/样式资源均返回 200**。启动日志正常、错误日志为空。保持预览进程运行供用户刷新查看。
- 本次未编辑 UI 或业务代码，未重新运行界面测试；HTTP/资源恢复不替代浏览器截图、页面渲染与四档宽度验收。

## 2026-10-24 新 FastAPI 身份/订单兼容与完整交接

用户在要求交接后追加新 API 登录/订单实现。本轮新增 modules/compat 的 10 个路由、service/ports 与本机 HTTP gateway；只调用旧唯一 writer，没有切换权威库。前端显式兼容开关仅覆盖该白名单。新增 0006、AI 接手主文档并更新入口说明与实际生成契约。

### 实际失败与修复

- 先运行两项接口测试，看到新增登录和订单入口均为 404，而期望分别是未配置 503 和未登录 401，再实现。
- 隔离命令环境的 TestClient 线程调用挂起，中止后在获准的隔离环境外运行同一合成测试；未修改系统配置或降低安全参数。
- 新前端两项用例先因仍请求旧路径、未解封套及缺失错误编号失败，再实现显式领域切换。健康能力标记测试先因 decode 丢字段失败，再修复。新测试 fetch mock 的参数类型与 Python JSON 边界类型检查错误随后已修正，未关闭严格检查。
- 重新生成 OpenAPI 和前端声明后，健康解码因缺少 compat_enabled 未通过类型检查；补运行时校验后重新完成全部前端检查和两种构建。早前该次构建命令不能替代最终通过结果。

### 最终执行与结果

- 本机项目 API Python **3.13.12**；`ruff check src scripts tests`、`ruff format --check src scripts tests`、mypy 均通过；mypy 检查 **22 个源码文件**。
- 新 API `PYTHONPATH=src` 下 unittest：**30 项通过，3.085 秒**。包含新增 9 项路由/权限/参数/原键/故障/配置、3 项 HTTP 边界，以及 1 项真实回环 HTTP + 临时 SQLite 集成，其他原有测试也运行。Starlette/httpx TestClient 存在上游弃用提示，未为消除此提示随意升级依赖；合成异常用例预期记录 request_failed。
- 集成测试仅在新建 artifacts/refactor/compat-integration-* 临时目录运行，清空该测试上下文 HC_DB，使用随机回环端口。真实旧服务注册三个合成账号，上传三张合成角度图并发布商品；通过新 API 完成登录、me、下单、同内容原键返回同单、列表、旁观账号 403、付款→卖家确认时间→交付→买家交接→收货完成、退出后 me 返回 401。结束关闭服务并清理该临时目录。
- 正式前端 ESLint 零警告、Prettier、vue-tsc 通过；Vitest **15 文件、41 项通过，9.30 秒**。
- 实际运行 API export_contract 与 openapi-typescript CLI，更新 contracts/openapi.json 和 generated.d.ts；手写前端仍为 JavaScript。
- 默认 Vite 构建与 `VITE_HUALI_COMPAT_API=1` 的 trial 构建均成功，命令退出码 0；trial 在 dist-trial，默认产物仍未开放业务。兼容环境变量随后恢复，不修改系统全局变量。
- `git diff --check` 通过，仅报告原工作区 LF/CRLF 提示。新增代码/文档尚未提交或推送，本轮未读取 GitHub CI 新结果。

### 尚未验证与交付边界

本轮不是旧后端全量回归、浏览器业务验收、微信真机、Worker/D1/R2 或生产验收。旧本地 SQLite checkout 的异内容原键请求摘要校验/编辑后重放与 Cloudflare 不同；本次同内容重放成功不能覆盖这些缺口。compat 仍是过渡边界，整站 business_ready 保持 false。

AI 智能客服代码在对方电脑，未取得、未运行、未调用模型供应商；主交接文档中的 AI API 和模块布局属于建议合同，需由对方核对。社区/论坛/消息/订单的新视觉稿仍在独立评审目录，未在本轮应用。

新前后端接手包独立于旧前端 ZIP；打包时显式选择改动源码、契约、文档、trial 产物和只读评审源码/合成素材，排除依赖、环境、日志、数据库与用户上传；包内 manifest 与包外摘要用于换机核对。不自动部署或覆盖已有工作区。

打包实测：93 个源码/文档/测试文件、46 个 trial 构建文件、29 个独立评审源码/素材文件，加 4 个说明与校验元数据，共 **172 条**。重新打开 ZIP 后 CRC、逐项字节和逐文件 SHA256 核对通过；文档定稿后再生成并重复核对，最终摘要见包外同名 `.zip.sha256`，避免把旧包摘要当作本轮值。

### 用户授权后的打包/推送准备

用户明确授权本批提交推送。只读核对 origin 的原 release 分支仍为 e611c310，未发现远端新提交；已有工作区差异保持。独立评审源码、配置和公开合成资源本次显式纳入 Git，运行产物和日志不纳入；新增评审 README。打包脚本改为相对基线列差异，并记录 SOURCE-REVISION，支持交付提交后重建。此前 172 条为授权前的包，最终条目与摘要按最新包中 manifest/包外 sha256 核对。

本次不修改业务逻辑；沿用上一节刚运行的 API 30 项、正式前端 41 项与构建结果，不声称本次再跑全部业务测试。提交前检查暂存文件、敏感内容标记、格式空白和包内 CRC/字节/摘要，提交后核对远端分支 SHA。GitHub CI 需区分已触发/运行中/实际通过，不把本机结果写成远端 CI 通过。
