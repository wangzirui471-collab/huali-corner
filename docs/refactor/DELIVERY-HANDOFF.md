# 华立转角重构：本批交付与接续手册

交付日期：2026-10-22（北京时间，跨越 10 月 21 日晚间开发）。

**这份手册描述实际交付，不把设计目标当作已完成功能。** 面向项目所有者、下一位开发者和接手 AI；仅凭仓库文件即可定位实现、启动、验证和继续工作。

## 1. 三分钟了解现在的状态

| 项目 | 实际状态 |
| --- | --- |
| 项目目录 | `C:\Users\90442\Desktop\前端学习\huali-corner` |
| 当前分支 | `release/2026-10-trial-hotfix` |
| 基线 HEAD | `b2b62660177f74b596a6add4fc030bd55354d9be` |
| 本批成果保存在哪里 | 按用户随后授权，通过 GitHub 的 `release/2026-10-trial-hotfix` 分支交付；最新提交用 `git log -1` 核对，`b2b6266` 仅为实施前基线 |
| 最新技术选型 | 手写前端 **JavaScript + Vue 3 + Element Plus**；后端 **Python/FastAPI** |
| 注释要求 | 新增和重构涉及的函数、方法、测试、任务脚本都有中文用途说明；关键权限、事务、异步恢复写清原因 |
| 可直接预览 | 新 Vue 组件样板；有交互表单、错误汇总、反馈和键盘弹窗 |
| 可运行的新 API | 健康检查、统一协议/错误边界、独立图片与原子计划基础；**业务尚未装配** |
| 旧业务处理 | 修补下单参数/幂等、媒体权限及旧客户端认证图片兼容，保留旧接口和原生小程序 |
| 尚未完成 | 全站 Vue 业务页面、完整领域拆分、真实平台验收、数据迁移与上线 |
| 本次停止位置 | 现有表单、图片兼容和检查已收尾；后续阶段只登记，**本次不再开展新功能任务** |

不要仅 checkout 基线 `b2b6266` 就以为拿到了本批代码。接手时获取该分支的最新交付提交，并检查本地是否还有其他未提交修改；保留任何后续工作区成果。不要执行 `git reset --hard`、`git clean` 或覆盖用户原有六份设计文档。

## 2. 用户已经确认的约束

1. 从本目录 README 及 01–05 六份文件出发重构整个项目，保留业务数据、账号、模拟交易、社区/论坛和原生小程序。
2. 前端选型已从原计划中的 TypeScript 改为 JavaScript + Vue 3 + Element Plus；后端继续 Python/FastAPI。生成的 `.d.ts` 只用于 JSDoc/checkJs 和编辑器提示。
3. 所有任务和方法加中文注释，让初学者能阅读。根目录 `AGENTS.md` 已落地这些要求。
4. 权威数据库暂不确定，要考虑兼容与扩展性。过渡期保留 SQLite/MySQL/D1 原路径；新增业务不能复制成多套独立 writer，更不能自动合并多库数据。
5. 保留紫色 ZJ、暖黄操作色、中文系统字体、紧凑双专题、五槽手机导航。新增 skill 的通用配色不覆盖品牌规范。
6. 用户最后要求：先完成正在开发的内容，出具交付手册，后续工作下次继续。没有安排定时任务或自动明日续跑。

## 3. 交付组成与代码定位

以下路径均相对于项目根目录。完整改动路径清单见 [DELIVERY-FILES.txt](./DELIVERY-FILES.txt)。

### 3.1 旧下单缺陷：A01 / A02

| 文件 | 修改内容与原因 |
| --- | --- |
| `Backend mission/app/cloudflare/trade_api.py` | 下单守卫用单个 JSON 快照与 `json_each` 核对 1–20 件商品，减少绑定参数；核对商品、卖家、价格、交付方式、求购和接受报价的原始快照。幂等键关联不可变请求摘要，订单后来修改或预约时间已过仍能恢复原请求结果，异内容重放拒绝。未知提交结果的恢复路径也核对请求身份。 |
| `Backend mission/app/cloudflare/schema.sql` | 新库的订单加入可空 `request_hash`。 |
| `infra/d1/migrations/0001_add_checkout_request_hash.sql` | 现有库的加法迁移，**没有应用到真实数据库**。 |
| `tests/test_cloudflare_trade.py`、`tests/test_checkout_migration.py` | 覆盖 20 件预算、求购不同、订单修改后重放、过期预约恢复、未知结果、旧库/新库迁移样例。 |

旧订单没有摘要时只能按旧字段保守比较，无法凭空还原修改前的原始请求。详见 [决策 0001](./decisions/0001-checkout-request-identity.md)。

### 3.2 媒体权限与旧客户端兼容：A04

| 文件 | 修改内容与原因 |
| --- | --- |
| `Backend mission/app/cloudflare/media_authorization.py` | 精确核对上传引用、资源归属、商品状态、订单参与人和工单上下文；角色名称不能直接绕过权限。 |
| `Backend mission/app/cloudflare/api.py` | 媒体入口调用资源授权；动态图片使用 `private, no-store`，避免私密图片被共享缓存。 |
| `web 7M/src/core/authenticated-media.js` | 旧 Web 的 `<img>` 无法发送 Bearer，因此在严格同源媒体路径加载失败时带认证读取 Blob；不把令牌放进 URL，不向第三方发认证头。 |
| `web 7M/src/main.js`、`core/state.js`、`router.js`、`auth/login.js` | 安装兼容器；换页/换账号时取消请求、阻止旧图迟到、回收 Blob URL。 |
| `web 7M/miniprogram/app.js` | 私密媒体通过 `wx.downloadFile` 携带 Bearer；登记临时文件，拒绝旧会话结果并清理文件。 |
| `web 7M/miniprogram/pages/detail/index.js`、`index.wxml` | 详情接入认证图片；隐藏/卸载清空私密内容，迟到请求不能重新填入；无权图片显示失败说明，保留收藏、报价、清单、私聊、分享的原接口。详情文件拆开排版并补中文方法注释。 |
| `tests/test_cloudflare_media.py`、`tests/test_cloudflare_catalog.py`、`tests/private_media.test.mjs` | 验证服务端授权、Web Blob 兼容及小程序真实页面生命周期代码；微信平台边界使用合成响应，不是真机验收。 |

权限摘要：在售且卖家正常的商品图可公开；上传者可预览自己的图；历史订单图只对合法参与者开放；凭证仅本人，或带具体 `ticket_id`、已认领且无利益冲突的处理员工。详细条件见 [决策 0003](./decisions/0003-resource-media-authorization.md)。

**微信接入限制：** 部署时还需核对微信后台的 downloadFile 合法域名、实际临时文件行为及真机权限；本机没有执行微信开发者工具编译或真机检查。临时文件不保存到相册或持久业务缓存。

### 3.3 新 Python/FastAPI 工程基础

| 目录/文件 | 已实现职责 |
| --- | --- |
| `apps/api/src/huali/bootstrap.py` | 唯一组合根 `create_app`，集中装配，不在业务模块随意创建应用。 |
| `shared/settings.py` | 必须显式提供 `HUALI_ENV=local/test/production`，缺失拒绝启动，不自动选空库。 |
| `transport/` | v1 封套、校验/业务/HTTP/未知错误映射、服务端 request_id、禁止缓存；内部异常细节不回给用户。 |
| `infrastructure/d1/atomic.py` | 检查绑定参数与 SQL 字节预算；期望影响行数在同一个 batch 内通过命名 CHECK 约束断言，避免伪事务与检查后竞态。 |
| `infra/d1/migrations/0002_create_atomic_assertions.sql` | 新适配器所需断言表；**未用于真实库**。 |
| `infrastructure/images/normalize.py` | 真格式白名单、字节/像素限制、静态图片、EXIF 方向、清除元数据、WebP 输出及摘要；头像最大 512 边，商品最大 1600 边。 |
| `apps/api/tests/` | HTTP 协议、原子失败注入、依赖边界和图片行为共 17 项。 |
| `apps/api/scripts/export_contract.py` | 从实际模型导出 `contracts/openapi.json`；目前仅健康接口。 |

新 API 的 `/health`、`/api/v1/health` 返回 `business_ready=false`。**它没有登录、商品、订单等业务路由，没有新 writer，也没有接入生产数据库。** 不要将健康接口成功等同于业务重构完成。

### 3.4 新 JavaScript / Vue 3 / Element Plus 前端

| 目录/文件 | 已实现内容 |
| --- | --- |
| `apps/web/src/app/` | 应用、路由、开发组件样板、默认未开放页面。默认生产构建不开放 `/_dev/components`；开发或显式 preview 模式开放。 |
| `shared/design-tokens/tokens.css` | 从 04 落地品牌/语义色、字体、间距、圆角、层级和动效令牌。 |
| `shared/ui/` | Element Plus 适配按钮、弹窗、输入字段、状态标签、持久提示、页面六类状态、可聚焦的表单错误汇总。 |
| `ComponentGalleryPage.vue` | 可实际提交的本地表单：提交后校验，聚焦错误汇总，通过链接定位字段；保留输入；修正后明确提示“尚未发布商品”，继续编辑撤销旧通过结果。 |
| `shared/http/client.js` | 同源 v1 请求、封套与 DTO 校验、CSRF/幂等头、Retry-After、未知写入结果处理；服务端 5xx 不自动清登录。 |
| `shared/http/request-scope.js` | 页面/账号变化时取消请求，忽略迟到响应。 |
| `shared/http/generated.d.ts` | OpenAPI 生成工具提示类型；不是手写 TypeScript 业务。 |
| `eslint-rules.js`、`jsconfig.json` | 中文具名方法注释检查、严格 checkJs 与 Vue 模板检查。 |

已使用新装 `ui-ux-pro-max` 优化表单反馈、焦点、触控目标、响应式和可读性；按 `tdd` 在用户确认的前端入口完成两个失败→实现→通过循环。具体查询、取舍及架构 skill 缺失依赖见 [skill-usage.md](./skill-usage.md)。

**还没有新的业务首页、完整五槽导航、登录、真实商品发布或新旧 hash 路由桥接。** 组件预览不能当作整站新前端交付；样板输入不发送商品写入请求。

### 3.5 本地 Worker 探针与协作工具

- `experiments/worker-poc/`：独立名称、`remote:false` 的 D1/R2、本地 ASGI/Cron/静态路由、回滚、20 行 JSON batch、旧 KDF、R2 和图片探针。探针接口仅供本地合成能力验证，缺少正式业务认证，禁止直接部署。
- `scripts/refactor.ps1`：Setup / Check / Contracts / Api / Web 五种任务，遇到工具失败停止，支持中文/空格路径。
- `.github/workflows/refactor-checks.yml`：新工程检查、协议漂移、旧后端回归和所有 `.test.mjs` / `.test.js` 客户端脚本；**尚未推送或在 GitHub 执行**。
- `.github/pull_request_template.md`、根 `AGENTS.md`、决策 0001–0005：落地增量开发和交付规则。
- `tests/user_center.test.mjs`：修正 Windows 中文路径 URL 解码，不改变业务断言。
- `.gitignore`：排除依赖、缓存、运行产物、PoC 同步副本等；不能把整个虚拟环境提交进仓库。

## 4. 进度：按任务门槛说明，不使用虚假的完成百分比

| 原计划任务 | 本批进度 | 剩余门槛 |
| --- | --- | --- |
| T00 基线与问题 | 已核对分支与工作区、补依赖、跑旧回归、修 A01/A02/A04 | 旧首页/详情/发布/订单/聊天/工作台的角色与视口截图基线不完整；行为矩阵还未全部变为可执行样例。 |
| T01 平台路线 | 多项本地 Worker 能力已实测；图片算法与打包差异已有证据 | 真实隔离平台 CPU/内存/冷启动、D1 并发与完整业务事务、Cookie/CSRF、Cron 补偿等未验收；见下一节的版本及 TLS 限制。 |
| T02 工程基础 | 新 API、Vue/Element Plus、工具、契约、基础原子/图片适配器、组件预览已落地 | 正式 Worker 组合根、真正 D1 FFI 接入、旧新业务 DTO mapper 与领域服务仍待完成。 |
| T03 登录—首页—含图发布—详情 | **尚未完成，未启动整条业务迁移** | 要在依赖门槛明确后实现旧凭据兼容、会话/Cookie/CSRF、资源服务和真实 Vue 页面，并做旧 Web/小程序兼容验收。 |
| T04–T07 订单/售后/社区聊天/工作台 | 尚未迁移 | 仍由旧业务实现承载；A01/A02 的修复不是订单领域重构完成。 |
| T08 数据迁移与恢复 | 未执行 | 权威写源未确认，未连接真实资源，未做隔离副本迁移/恢复/对账。 |
| T09 发布与退役 | 未执行 | 未部署、未切流量、未关闭旧 writer、未退役旧代码。 |

## 5. 验证结果、失败记录及其边界

| 验证 | 实际结果 | 范围与限制 |
| --- | --- | --- |
| 旧 Python 完整回归 | 本轮早些时候 **480 项通过，约 149 秒** | Python 3.12.14 + Pillow 12.3.0 + PyMySQL 1.2.3；之后的收尾改动是客户端兼容与新工程，没有重新声称跑过另一轮 480 项。 |
| 旧客户端脚本 | 收尾重新运行 **11/11 脚本通过** | 包括三个原生 `.test.js` 及新媒体兼容脚本；合成平台边界不是真机。 |
| 新 API | **17 项通过** | Ruff 检查/格式与严格 mypy 通过；故障注入的 request_failed 日志是预期场景。Starlette 对 httpx 有弃用提示，未影响结果。 |
| 新前端 | **11 项通过** | ESLint/Prettier、checkJs/Vue 模板检查、默认生产构建通过。两个页面表单测试通过可见 DOM 和焦点断言，不读取内部状态。 |
| 预览构建与契约生成 | **收尾通过** | 显式 preview 构建包含样板，随后重新默认构建恢复关闭开发路由的产物；重新生成 OpenAPI/声明后，两文件 SHA256 与生成前一致。 |
| 实际浏览器 | 表单错误汇总、Tab/Enter 定位、修正后反馈；弹窗打开/Escape/焦点返回 | 320/390/768/1440 目标宽度无页面横向溢出；不是旧全站的视觉基线。 |
| 本地 Worker 基础探针 | 本轮曾实际通过 | ASGI、后续 CHECK 失败整体回滚、20 行 JSON batch、R2、重复本地 Cron、API/media JSON 404、SPA 深链、600000 轮合成旧 KDF 向量。 |
| 本地 Worker 图片探针 | 本轮曾实际通过 | Pillow 12.2.0，JPEG/PNG/WebP、EXIF、头像缩放、20M 合成像素、5 MiB 填充 JPEG、超限/截断/动画拒绝、R2 回读。不是云端资源预算或任意照片压力证明。 |
| Worker 收尾重启复核 | **未通过，单独保留失败** | 同步源码触发重载后，workerd 报 `kj/compat/tls.c++:429 ... peer disconnected without gracefully ending TLS session`；图片请求连接被重置。停止旧实例并用同一隔离配置重启一次，仍在启动阶段遇到 TLS 错误。不能把此前通过写成“最终环境可稳定复现”。 |
| GitHub CI、微信真机、隔离云端与生产 | 本地交付收尾时未执行 | 推送会触发新 CI，具体结果查看 GitHub Actions；没有据此作全部验收或上线声明。 |

### 图片运行时的明确限制

新 API 锁 Pillow **12.3.0**；当前 Worker SDK 兼容索引仅为探针解析到 **12.2.0**。后者缺少 12.3.0 的部分安全修复。**只允许本地合成能力验证，不能据此直接采用 12.2.0 接真实上传。** 详见 [决策 0005](./decisions/0005-worker-image-runtime.md)。

KDF 内部计时约 0.98–0.99 秒、20M 合成图片约 0.72 秒，都是早前本机墙钟观测，不是云端 CPU 计费、峰值内存、并发或 SLA。不要为满足预算降低旧 KDF 的 600000 轮数。

## 6. 拿到项目后如何启动和验收

### 6.1 先核对交付提交与本地修改

```powershell
# 任务：核对接手位置、最新交付提交与本地修改；以下均在项目根目录执行。
Set-Location 'C:\Users\90442\Desktop\前端学习\huali-corner'
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
git status --short
```

新工程与文档是本批新增目录，已纳入本批交付提交；`DELIVERY-FILES.txt` 的 M/?? 是提交前快照，不能当作当前状态。若接手时仍有未跟踪文件，先核对来源，不直接删除。先阅读根 `AGENTS.md`，再读本手册、`verification.md`、决策及相关 01–05 章节。

### 6.2 安装及检查新工程

需要 Node.js 22.12+、Python 3.13/3.14 和 uv 0.13.4。本机已使用 Node 24.21.0、新 API Python 3.13.16；旧业务回归另用 Python 3.12.14。新旧虚拟环境不要混用。

```powershell
# 任务：使用锁文件准备新工程；需下载公开依赖，已安装时不必重复执行。
powershell -ExecutionPolicy Bypass -File .\scripts\refactor.ps1 -Task Setup

# 任务：新 API 的 Ruff/mypy/17 项测试，以及前端格式/类型/11 项测试/构建。
powershell -ExecutionPolicy Bypass -File .\scripts\refactor.ps1 -Task Check

# 任务：从实际后端模型更新 OpenAPI 与前端生成声明；不是手写业务类型。
powershell -ExecutionPolicy Bypass -File .\scripts\refactor.ps1 -Task Contracts
```

Setup 可回退使用项目忽略目录 `.local-deps/bin/uv.exe`；这些本机依赖不随 Git 移交，换机器需要安装 uv。`PYTHONUTF8=1` 由任务入口设置，避免中文路径编码问题。

### 6.3 查看前端样板和新 API

```powershell
# 任务：在终端一启动新 API，仅监听 127.0.0.1:8001，不连接真实业务库。
powershell -ExecutionPolicy Bypass -File .\scripts\refactor.ps1 -Task Api

# 任务：在终端二启动组件样板；5173 被占用时明确选择 5186。
npm --prefix apps/web run dev -- --port 5186
```

访问 `http://127.0.0.1:5186/_dev/components`；API 查看 `http://127.0.0.1:8001/api/v1/health`。开发预览和正式构建的路由开关不同，默认 `npm run build` 只开放未就绪说明页。`npm --prefix apps/web run build:preview` 是显式预览构建，不能替代正式业务发布包。

人工验收步骤：

1. 保留预填标题、交付地点留空，点击“检查填写内容”；焦点应到错误汇总，标题不能丢。
2. 按 Tab 再按 Enter 激活错误链接；焦点应到交付地点。
3. 填公共交付地点再次检查；显示“填写检查通过”和“尚未发布商品”，错误清除。
4. 继续编辑；旧通过提示应撤销。两个字段留空时，汇总应有两项。
5. 点击“发布商品”样板按钮；弹窗出现，Escape 关闭，焦点回到按钮。此处不会创建真实商品。
6. 用 320/390/768/1440 宽度检查长文案、错误状态和无横向溢出。

### 6.4 旧客户端脚本与旧后端回归

```powershell
# 任务：执行全部旧 Web/原生客户端脚本，任一失败即停止。
$clientScripts = @(Get-ChildItem tests -File | Where-Object { $_.Name -match '\.test\.(mjs|js)$' })
foreach ($clientScript in $clientScripts) {
    node $clientScript.FullName
    if ($LASTEXITCODE -ne 0) { throw "客户端验证失败：$($clientScript.Name)" }
}

# 任务：用独立旧环境执行完整业务回归；不覆盖 apps/api 的虚拟环境。
uv run --no-project --python 3.12 --with Pillow==12.3.0 --with PyMySQL==1.2.3 python -B -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

### 6.5 本地 Worker 探针

完整命令见 [探针 README](../../experiments/worker-poc/README.md)，先设置 `PYTHONUTF8=1`，从该目录 `uv sync --locked`、`npm ci`，运行 `sync_sources.py`，初始化**隔离本地** schema，再 `uv run pywrangler dev --test-scheduled`，另一个终端运行 `image_smoke.py` 和 `smoke.py`。

启动时必须看到 DB、MEDIA、ASSETS 为 local；若再遇到本手册记录的 TLS 启动错误，保留失败与版本信息后排查运行时下载/网络，不改变业务 SQL 或安全参数来掩盖启动故障。**不要用 `Backend mission/wrangler.jsonc` 代替本地配置，其中存在 `remote:true`。**

## 7. 数据、发布与回滚说明

- 本批未连接或改写真实 D1、R2、SQLite、MySQL；未导入用户数据、修改真实账号或启用付费资源。
- `0001` 是旧订单请求摘要加法列。上线旧 Worker 修复前，先只读核对目标 schema，再只应用一次；不要盲目重复 `ALTER TABLE`。
- `0002` 服务于新原子适配器。仅添加它不意味着新业务接入完成；按隔离演练结果再应用到后续目标。
- 当前没有必要回滚真实数据。代码撤回时保护用户原文件、保留兼容加法列；不能将新写入切回不理解其语义的旧 writer。
- 真实发布前仍需要权威源确认、一致备份、隔离恢复、引用/金额/状态对账、单一写入口与可审阅回退方案。详见 05 §3。

## 8. 下次继续的既定顺序

这里登记原计划剩余工作，**本次不执行，不额外扩展范围**。

1. **先核对交付与环境。** 保留工作区，复跑新工程和相关客户端检查；解决本地 Worker 的 TLS 启动复现问题，确认维护中的图片依赖路线。不要无故重写已经通过的模块。
2. **补齐 T00 的真实页面基线。** 用合成数据记录旧首页/详情/发布/订单/聊天/工作台及角色、视口；组件预览截图不能充当这些证据。
3. **完成 T01 依赖门槛。** 在可审阅的隔离资源方案下验证真实平台 D1 事务/并发/参数、KDF/图片 CPU 和内存、Cron、Cookie/CSRF 与路由。根据证据确定 Worker 或 02 的外部 FastAPI 备选，不任意更换数据库。
4. **补齐 T02 后再做 T03。** 接入正式组合根/适配器、旧新 DTO mapper；随后实现登录—首页—含图发布—详情的第一条完整业务切片，复用现有 Element Plus 组件和品牌令牌。
5. **后续按 T04→T05/T06→T07→T08→T09 推进。** 订单账本、售后定时、社区聊天、工作台依次迁移；最后完成数据恢复演练、发布和旧实现退役。

数据库权威源未确认时，继续做不依赖真实数据的离线实现和只读方案；迁移前必须明确唯一 writer。对比 DB、备份和部署时不把私密内容写入 Git 或公开报告。

## 9. 交给下一位 AI 的可复制提示词

```text
你接手华立转角重构，工作目录 C:\Users\90442\Desktop\前端学习\huali-corner。
先读 AGENTS.md、docs/refactor/DELIVERY-HANDOFF.md、verification.md、决策 0001–0005，
再查 README 与 01–05 的相关章节。不要只读设计文档就假设目标已实现。

分支 release/2026-10-trial-hotfix；b2b6266 是实施前基线，本批已按用户授权纳入交付提交。
先核对 git log -1 和 git status，获取该分支最新交付，保留用户六份文档及后续修改；不 reset/clean。
手写前端 JavaScript + Vue 3 + Element Plus，后端 Python/FastAPI；每个新增或重构方法、
任务与测试加中文注释。生成 .d.ts 仅作工具提示，不改回 TypeScript 业务实现。

已有 A01/A02 下单修复、A04 资源授权与 Web/小程序认证图片兼容；新 API/Vue 工程基础、
表单交互和协议工具已经落地。T00–T02 仍有门槛，T03 业务切片没有完成，
绝不能把健康检查或组件样板当作整站重构完成。

已验：旧后端本轮较早 480 项通过；收尾旧客户端 11 个脚本通过；
新 API 17 项、Vue 11 项和格式/类型/构建通过；具体边界以手册为准。
本地 Worker 曾通过平台与图片探针，但收尾重启遇到 workerd TLS 断连，重试仍失败。
正式 API Pillow 12.3.0，探针 12.2.0 仅合成验证，不可直接用于生产上传。

数据库权威源未知，真实 D1/R2、迁移、微信真机、云端资源尚未验收；推送后的 CI 结果须另外核对。
本批没有部署，没有真实数据修改，不使用旧 remote:true 配置验证本地探针。

用户上次要求收尾交接后暂停新增功能。只有用户本次明确要求继续，才按手册第 8 节
选择一个既定切片推进；先报本轮范围与验收，再实现和更新记录，不同时铺开全站。
```

## 10. 交付文件与证据怎么保存

- 源码/配置/锁文件/测试/手册：见 [改动文件清单](./DELIVERY-FILES.txt)。六份原文档是用户提供的设计资料，本批只补充当前技术栈、进度和入口说明。
- 实测时间与历史结果：[verification.md](./verification.md)；架构理由：[decisions/](./decisions/)；skill 使用：[skill-usage.md](./skill-usage.md)。
- 最终手机和桌面截图已纳入 `docs/refactor/evidence/`，可随本批源码交付，见下图。原始截图保存在本机忽略目录 `artifacts/refactor/`；其中 `components-{320,390,768,1440}.jpg` 为早前组件证据，320/768 的 form 截图早于最后的输入框撑满调整。只复制 Git 源码时不会包含这些历史截图。
- 依赖/运行产物 `.venv`、`node_modules`、`.uv-*`、`.wrangler`、`python_modules`、PoC `src/huali`、`dist` 不交入源码；按锁文件重建。
- 用户在本地交付后授权提交到原 GitHub 分支，本批按该分支直接提交交付；没有创建 PR 或执行部署。本批启动的 Vite 5186 和 Worker 8787 均已停止，并核对这两个端口已无监听；临时浏览器预览页已关闭。未处理其他进程或已有的 5173 服务，下次按第 6 节重新启动。

**本批交付的完成标准：现有改动可定位、已运行的检查有结果、失败与剩余门槛明确、接手者能按命令继续。全项目重构仍按上述阶段推进。**

### 最终界面证据

桌面表单（1440 目标宽度，焦点位于错误汇总）：

![桌面表单及错误汇总](./evidence/form-1440.jpg)

手机表单（390 目标宽度）：

![手机表单及错误汇总](./evidence/form-390.jpg)
