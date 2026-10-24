# 给下一位 AI：华立转角接手、前后端与智能客服对接

更新：2026-10-24。先读本文，再读具体规范。本文区分已实现接口、隔离验证和建议合同，不能把设计当成已上线成果。

## 1. 先找对工作区和代码

当前根目录：`C:\Users\7M\Desktop\前端\huali-corner-refactor`。

分支 `release/2026-10-trial-hotfix`；开发基线 `e611c31084aae51f46b5fe94ff1802d0736eb50b`。用户已授权将本轮前端候选、新 FastAPI 兼容入口、文档和独立评审源码提交推送到该分支。接手时拉取该分支最新交付，并核对远端提交与本次交付汇报；**e611c310 只是基线，不是包含本批新增功能的最新提交**。包内 SOURCE-REVISION.txt 记录打包时提交。另一台电脑盘符不必相同，以实际 Git 根为准。

旁边的 `huali-corner-trial` 是另一个已有修改的工作区，不能覆盖。`b2b6266` 是历史重构前基线，禁止回退覆盖成果。

| 位置（相对项目根） | 内容与当前状态 |
| --- | --- |
| `apps/web/` | 新 JavaScript + Vue 3 + Element Plus 前端候选；并非全部浏览器验收完成 |
| `apps/web/src/app/router.js` | 页面入口及 dev/trial 开关 |
| `apps/web/src/features/` | identity、catalog、trade、support、community、workspace 业务页面 |
| `apps/web/src/shared/legacy/` | 旧 DTO、Bearer、取消/恢复及新 FastAPI 兼容开关 |
| `apps/web/src/shared/http/` | 新封套客户端、健康解码、请求作用域、自动生成声明 |
| `apps/api/` | 新 Python/FastAPI 工程，当前项目环境 Python 3.13.12 |
| `apps/api/src/huali/bootstrap.py` | 唯一装配位置；`main.py` 为 ASGI 入口 |
| `apps/api/src/huali/modules/compat/` | 本轮新增登录与订单兼容路由、输入模型、用例与依赖端口 |
| `apps/api/src/huali/infrastructure/legacy.py` | 连接显式本机旧服务的 HTTP 适配器 |
| `Backend mission/app/` | 旧业务规则与唯一账号/订单 writer，暂未退役 |
| `Backend mission/server.py` | 本地旧服务；Cloudflare 旧入口在 `app/cloudflare/` |
| `contracts/openapi.json` | 根据当前新 FastAPI 实际路由生成；不是手写目标接口清单 |
| `artifacts/refactor/ui-preview/` | 5198 合成界面评审宿主；源码/配置/合成素材随本次提交显式跟踪，运行产物仍忽略；不是真实业务服务 |
| 对方电脑上的 AI 模块 | 用户确认代码在对方处，本工作区未取得、未审查、未运行 |

当前仍是模块化单体的渐进迁移，不是微服务改造；不引入另一套交易数据库、独立业务 writer 或消息中间件。

## 2. 已经做到什么，不能误报什么

- T03–T07 的前端候选已写，包含身份、商品、订单、工单、社区/论坛/消息和分权工作台；不等于对应阶段完整完成。
- 首页、商品卡片和五槽导航的方案已获用户确认并应用。社区、论坛、消息、订单的差异化布局仍在独立评审副本，未据此覆盖正式业务组件；售后等其他页面也不能冒称已完成同样的视觉调整。
- 本轮新 FastAPI 已增加登录、查询当前身份、退出、订单列表/详情、下单、订单动作、付款前修改和改约决定的**兼容入口**。它把经校验的请求交给原 writer，不复制旧 SQL、密码算法、定价或状态机。
- 新 API 健康数据仍为 `business_ready=false`；`compat_enabled=true` 只说明装配了兼容依赖，不代表上游已探活、全站迁移或生产验收通过。
- 默认生产前端仍显示未上线入口；业务页面用 dev 或 trial。没有执行生产部署、真实数据迁移或旧系统退役。
- T00–T02 仍有门槛待补；T08 是迁移/兼容/恢复演练，T09 是发布切换/单一写路径与退役，均未完成。

## 3. 当前前后端具体怎样连接

```text
Vue（5173 开发 / 4173 trial）
 ├─ 未切换的业务 /api/*、媒体 /media/* → 旧服务 8081
 └─ 显式开启身份/订单兼容开关
      → 同源 /api/v1/compat/* → 新 FastAPI 8001
          → CompatService → LegacyGateway → 旧服务 8081 → 原业务事务

5198：另一个只读合成宿主，用来评审界面，不参加上面的真实业务联调。
```

浏览器只请求本站相对地址；端口代理见 `apps/web/vite.config.js`。不把浏览器直接指向模型供应商或任意服务地址，不使用 CORS 全开放来掩盖配置错误。

### 3.1 已实现的新接口

以下路径均以 `/api/v1/compat` 开头，返回现有 `Envelope` 封套，其 `data` **刻意保留旧 DTO**：数字 ID、金额整数分、时间秒。规范化新 v1 业务的字符串 ID/毫秒规则不自动套在 compat 上。

| 方法与路径后缀 | 实际旧入口 | 认证/说明 |
| --- | --- | --- |
| GET `/auth/salt?phone=...` | `/api/auth/salt` | 保留盐和轮数；不带 phone 时需登录 |
| POST `/auth/login` | `/api/auth/login` | `phone` 与 `password` 或 `digest` 二选一 |
| POST `/auth/logout` | `/api/auth/logout` | 原 Bearer；撤销原会话 |
| GET `/me` | `/api/me` | 原 Bearer，由服务端核验身份 |
| GET `/orders` | `/api/orders` | 当前账号的订单 |
| GET `/order?id=...` | `/api/order` | 原服务核对订单可见范围 |
| POST `/checkout` | `/api/checkout` | 原 `key`、商品 ID、交付方式和预约；不接收自报金额/卖家 |
| POST `/order/action` | `/api/order/action` | pay/cancel/confirm_schedule/deliver/handover/receive/reschedule |
| POST `/order/update` | `/api/order/update` | 付款前修改，权限和状态仍由旧规则检查 |
| POST `/order/change` | `/api/order/change` | 已有改约的接受/拒绝 |

旧 DTO 是本兼容边界的明确例外，不能把其数字 ID 直接复制为未来所有新 API 的标准。模型与 OpenAPI 是请求字段的直接依据。注册、改密、恢复、商品、售后、报价和评价等未列出的操作仍使用旧 `/api/*`，没有假装全部迁移。

Bearer 是原系统的不透明会话，不是新增 JWT。Cookie/CSRF 目标会话尚未落地，禁止仅因 `shared/http` 支持同源 Cookie 就认为服务端已支持。

### 3.2 启动方式：全部从项目根目录，三个终端

Node 需要 22.12+；本机已用 24.19.0，不要用 PATH 中的 Node 18。新 API 需要 Python 3.13/3.14，不能用应用自带的 Python 3.12 启动其 3.13 语法。

已有项目依赖可复用，不必重新安装。新电脑可通过 `scripts/refactor.ps1 -Task Setup -PythonExecutable '<本机已有3.13/3.14路径>'` 准备项目环境；需要现有 uv 0.13.4 和合适 Node/npm。只装项目依赖，不安装 Docker、WSL 或全局 Python 包，不复制虚拟环境或 node_modules。

终端 A：使用全新的合成目录启动旧唯一 writer；需要时先按 `FRONTEND-TRIAL-HANDOFF.md` 创建 `.venv-trial` 并安装旧 requirements。

```powershell
# 只影响本终端，避免意外使用原数据库选择或预设管理员。
$env:HC_DB = ''
$env:HUALI_ADMIN_PHONE = ''
$env:HUALI_ADMIN_PASSWORD = ''
$trialData = Join-Path (Get-Location) ('artifacts/acceptance-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& .venv-trial/Scripts/python.exe 'Backend mission/server.py' --trial --host 127.0.0.1 --port 8081 --data $trialData --public-origin http://127.0.0.1:5173
```

终端 B：启动新 FastAPI，将其兼容依赖明确指向终端 A。

```powershell
$env:HUALI_ENV = 'local'
$env:HUALI_LEGACY_ORIGIN = 'http://127.0.0.1:8081'
& apps/api/.venv/Scripts/python.exe -m uvicorn huali.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8001
```

终端 C：显式切换已实现的身份/订单入口，其他领域仍走原服务。

```powershell
$env:HUALI_LEGACY_ORIGIN = 'http://127.0.0.1:8081'
$env:VITE_HUALI_COMPAT_API = '1'
npm --prefix apps/web run dev
```

打开 `http://127.0.0.1:5173`；新 API 接口文档在 `http://127.0.0.1:8001/docs`，健康接口为 `/api/v1/health`。8001 不负责提供 Vue 页面。

如改用 trial：保留 `VITE_HUALI_COMPAT_API=1` **在构建时生效**，运行 `npm --prefix apps/web run build:trial`，再 `npm --prefix apps/web run preview:trial` 打开 4173，并将旧服务的 public-origin 改为 `http://127.0.0.1:4173`。只在 preview 启动后设置变量，不能改变已编译脚本。

兼容依赖未配置会返回 `503 LEGACY_NOT_CONFIGURED`；上游网络故障会返回 502。只有明确的 401 使前端清会话，502/HTML 不能让用户无故退出；写入结果未知时保留原键与草稿并先核对订单。新兼容配置当前禁止生产模式和远程源站，不扩大为任意 URL 代理。

### 3.3 当前边界与剩余风险

- 已验证的是本机合成 SQLite + 真实回环 HTTP，不是真实 D1/R2/Worker 验收。
- 新兼容入口不会自动重试写入，checkout 头/正文键不一致会拒绝；同内容重放实际通过。旧本地 SQLite checkout 与 Cloudflare 实现仍有差异：源码中本地重放直接取旧订单，未提供 Cloudflare 那样的不可变 request_hash 校验。**异内容原键冲突、编辑后的历史重放及并发回滚必须作为后续门槛补齐，不能声称本轮已完成全部幂等规则。**
- 订单的业务权限、金额和原子写最终仍依赖旧实现；本轮未将它们迁成新的 D1 用例。替换 adapter 不等于迁完底层规则。
- 旧服务的其他已知限制与另一电脑的浏览器验收清单见 `FRONTEND-TRIAL-HANDOFF.md`。不使用旧 remote:true，不降低 TLS 校验或 KDF 轮数。

## 4. 智能客服：对方先提供什么

代码在对方处，下面均为交接要求或建议，**当前没有 AI 接口可直接调用**。

请 AI 模块负责人提供：仓库/分支/提交 SHA、改动清单、模块入口、启动命令、Python/依赖锁、已实现 API 的请求响应例子、认证方式、同步或流式、历史与知识库保存位置、模型供应商和所需配置名、限流/超时/幂等实现、已运行测试。只提供配置名，不把密钥、真实会话或聊天全文塞进交接文档。

若两边基线不同，先比较差异并保存现有修改，按文件合并；不得整目录覆盖新前端或新后端，不让两个 AI 同时写同一 checkout。各用独立工作区或约定一个写入方。本对话未自动发送任何消息给对方。

## 5. 智能客服接在哪一层

推荐作为 support 领域的 assistant 子模块；不要给 AI 模块直接访问订单表、账本或退款 writer 的权限。

```text
Vue features/support/assistant（建议新目录）
  → 同源 /api/v1/support/assistant/answer（建议合同，尚未实现）
  → FastAPI 输入/认证边界
  → support/assistant/service：身份、上下文、检索、调用与转人工建议
  → KnowledgePort / ModelPort / IdentityPort
  → infrastructure 中适配对方的已有模型服务或现有 SDK

所有实现只在 bootstrap 装配，规则与应用用例不依赖供应商 SDK。
```

如果对方已经有独立 Python 服务，先保留其实现，通过服务端 ModelPort 适配，不必强制推倒重写；前端仍只调用本站 FastAPI。上游地址由服务端配置白名单控制，不能由聊天请求传任意 URL。

第一片只做公开规则 FAQ：非流式回答、来源、失败反馈与转人工入口。先不要读私密订单/聊天、持久化整段历史、上传证据或自动建工单。这样可以先把正确链路接通，之后逐项加入有权限的上下文。

### 5.1 建议合同（需要双方确认后实现）

```json
{
  "client_turn_id": "本次提问的固定UUID",
  "question": "怎样和卖家约定交付时间？"
}
```

建议 POST `/api/v1/support/assistant/answer`，成功沿用现有 Envelope；data 可为：

```json
{
  "client_turn_id": "与请求一致",
  "answer_text": "合成示例回答，实际内容来自已发布的规则资料。",
  "sources": [{"document_id": "faq-demo-001", "title": "示例交付规则", "version": "demo"}],
  "handoff": {"recommended": false, "reason": "", "next_path": "/support/new"}
}
```

约定：question 有非空和长度限制；client_turn_id 只关联本账号这次请求。不要让前端提交 user_id、role、系统提示词或完整数据库上下文；如果加入 conversation_id，服务端每次验证归属，不能仅凭 ID 读取历史。

第一片的来源只能指向服务端认可资料；模型编造的 citation 不能作为已验证来源。模型文本按纯文本/经过白名单处理的富文本显示，不能直接 v-html。无依据就说明无法确认并给转人工入口，不能用模型自报置信度代替证据。

### 5.2 认证与 HTTP 客户端不能漏接

现有 compat 用原 Bearer，新 `shared/http/client.js` 的默认能力主要为同源 Cookie/CSRF，**没有自动把旧 token 加到未来任意新路由**。不要把 AI 接口直接加入 COMPAT_PATHS，也不要假定新路由已经有身份。

建议先建立明确的 IdentityPort，使用组合根同一个 LegacyGateway 经原 `/api/me` 核实会话，再生成可信 actor；未来原生 identity 迁移时只替换该适配。对新 AI 客户端显式注入会话读取和 RequestScope，而不是在页面拼认证头。Bearer 只发给本站和配置的身份适配器，绝不送给模型供应商。

无效原会话 401；身份服务超时 503，不得误写 401 清用户会话。账号切换/离开页面取消旧请求，丢弃迟到回答并清私密内存；存储草稿按账号隔离。Cookie 会话正式落地时统一补 CSRF，而非新旧认证长期各做一套。

### 5.3 人工客服与订单上下文

现有用户界面为 `features/support/SupportPage.vue`；提交工单用旧 `/api/tickets`，工单详情 `/api/ticket?id=...`，在线客服 `/api/support/room`，其结果再进入 `/messages/:id`。

原规则要求用户有待处理工单才能联系在线客服；平台人员进入客服会话需显式认领 `/api/support/claim`。AI 转人工只能先建议去 `/support/new` 并预填用户可检查的草稿；用户明确提交后才创建工单/会话，不把示例 room_id 写死，不伪造客服认领。

以后加入订单 context：服务端按当前 actor 调用有权限的订单查询，白名单裁剪状态、金额和预约即可；不发送电话、恢复码、token、私密证据、内部备注或整库记录。AI 只能解释已核实状态，退款/取消/处罚仍走原业务权限、明确用户动作和唯一事务入口。模型输出与检索资料均是数据，不能覆盖系统权限规则。

### 5.4 超时、重试与模型配置

API Key 仅服务端配置，不放 VITE_*、前端包、Git 或日志。配置名由对方模块实际接口确定，不能照抄虚构的环境变量。上下文发送到外部模型前需要确认供应商、保存策略与授权范围，本轮没有做真实调用。

先用同步非流式，便于统一封套与失败处理。需要流式时单列合同，例如事件 turn/delta/done/error，定义断连恢复、完成标记、取消和代理行为；不能同时承诺 JSON Envelope 与未定义的 SSE 格式。

同一轮重试沿用 client_turn_id；服务端以 actor + turn_id + request_hash 隔离。没有持久状态及上游幂等证据时，不能宣称重启/超时后“绝不重复计费”。不在数据库事务中等待模型网络请求；异常保留输入，不假报回答成功，也不自动发第二个付费请求。

## 6. 后续开发按什么模式和规范

强制阅读：`AGENTS.md` → `DELIVERY-HANDOFF.md` 最新节 → `verification.md` 最新节 → 本文相关代码 → 01–05 相关章节 → decisions 0001–0006。

优先级：用户最新指令 > AGENTS 当前约定 > 已确认决策 > 历史设计示例。旧 03 中 TypeScript 示例不能覆盖 0004 的 JavaScript 选型。

| 方面 | 约定与可参照代码 |
| --- | --- |
| 前端语言/组件 | JavaScript、Vue 3 Composition API、Element Plus；参考 shared/ui 的品牌适配 |
| 页面与状态 | feature 页面组织用例；api.js 负责协议；composable 负责生命周期；shared 只放真正共用能力，不建巨大通用页面 |
| 视觉 | 共享令牌和基础行为，页面按用途组织信息；禁止所有内容套相同白框；保留紫色 ZJ、暖黄、双专题、五槽导航 |
| 前端安全边界 | 参考 shared/legacy/use-task.js 与 shared/http/request-scope.js；旧响应、定时器、Blob、监听器要清理 |
| 后端 | router/schema → service/use case → rules + ports；infrastructure 实现端口；bootstrap 装配。参考新 compat 模块的窄端口和故障映射 |
| 数据/权限 | actor 来自服务端会话；归属/状态/利益冲突由服务端核验；旧 writer 保留到对应新用例完整验收 |
| 事务 | 订单、库存、账本、通知、审计列清原子集合；参考 infrastructure/d1/atomic.py，但本机 SQLite 测试不是 D1 证据 |
| 协议 | 新规范 DTO 使用字符串 ID/整数分/UTC 毫秒；compat 保留旧 DTO；实际模型生成 OpenAPI 与前端声明，不手改 .d.ts |
| 注释 | 新增/重构函数、测试、脚本均中文 docstring/JSDoc；关键处解释权限、单位与失败恢复原因 |
| 测试 | 先写有意义的规则/合同/异常测试；UI 改动补四宽度浏览器检查；mock、真实隔离后端、Worker、真机结果分别记录 |

每轮一个明确切片，先说明实际进度与本轮目标。先完成具体可审阅结果，再按用户要求进入确认；不要先建全部空模块，不全仓格式化，不以降低校验换通过。涉及 UI 的新方向先独立预览，经用户确认再应用。

新增功能任务卡应包含：目标与非目标、唯一所属领域、入口/角色、API/单位/兼容、唯一 writer 与原子集合、失败/幂等恢复、页面六类状态、测试数据与验收、迁移/回退、本轮证据与剩余项。不要仅提交“新增一个页面”的描述。

建议顺序：先验收本轮身份/订单 compat → 补本地与 Cloudflare 幂等差异及异常 → 对方提供 AI 模块，接公开 FAQ 第一片 → 再逐域迁移新用例/真实平台门槛 → T08 → 经授权的 T09。

## 7. 检查、证据和交付

新 API：在 `apps/api` 执行项目环境内的 Ruff check/format、mypy、`PYTHONPATH=src` 的 unittest、export_contract。前端在 `apps/web` 执行 lint、typecheck、test:unit、generate:api、默认和 trial 构建。统一入口为 `scripts/refactor.ps1`，但应核对 Node 版本和本机解释器路径。

本轮已经实际运行：API **30 项通过**，含临时合成 SQLite + 真实回环 HTTP 的登录/下单/同内容重放/越权/双方完整交付/退出；正式前端 **41 项通过**，前后端风格/格式/类型与默认/trial 构建通过。详细失败与修复以 `verification.md` 最新节为准；旧后端全量、Worker、浏览器/真机验收没有被这次单链路替代。

正式 Pillow 12.3.0；Worker 探针 12.2.0 仅供合成能力证明。图片运行时路线与 Worker TLS 问题仍待处理，不降低证书校验或密码轮数。真实数据库权威源未确认，不自动合多库，不使用旧 remote:true。

移交时提供基线、实际交付提交、源码/文档/契约与校验摘要；勿复制依赖、数据库、用户上传、凭据或日志。生成 `artifacts/refactor/huali-refactor-handoff-20261024.zip` 及同名 `.zip.sha256`，按包内 manifest 核对条目、CRC、字节和逐文件摘要。这是基于 e611c310 的增量文件，必须合入全新的该基线副本，不能覆盖脏工作区；也可直接使用原分支已核对的最新交付提交。旧 20261023 前端 ZIP 不包含这次后端接入。对方的 AI 模块需单独提供并按其 SHA 合并。

## 8. 可直接转发给另一位 AI 的接手指令

> 接手华立转角当前工作区，先读本文件、AGENTS.md、交付手册和验证记录。核对 release/2026-10-trial-hotfix 最新交付提交及其相对 e611c310 的差异，保留已有本地修改，不 reset/clean。新前端在 apps/web，新 FastAPI 在 apps/api；登录/订单已通过 /api/v1/compat 接入旧唯一 writer，整站 business_ready 仍为 false。用全新合成数据和三个本机终端复现，不连接真实库或部署。你负责的 AI 智能客服先提供代码位置/SHA/合同/配置名/测试，再按本文 support/assistant + ports/adapter 模式接公开 FAQ，认证需核实原会话；不能直接读写订单/账本或冒充人工客服。每轮只推进一个完整切片，先报事实和目标，完成后更新交付/验证记录。前端手写 JavaScript + Vue 3 + Element Plus，后端 Python/FastAPI；方法/测试/脚本中文注释，UI 新方向先预览再应用。只报告真正运行过的结果。
