# AI 模块盘点与公开 FAQ 窄接入审查

日期：2026-10-24。本文区分旧实现事实、本轮新增边界和未验证事项；没有调用收费模型、生产环境或真实用户数据。配置只列名称，不包含任何实际密钥。

> 2026-10-25补记：本文是前轮本机公开FAQ来源盘点。后续发布只读核实发现线上5e7bd074的AI已比该旧分支更新，不能把下面6edfc13当作当前线上AI。已保留线上模块并完成宠物流式切片，见 [交付手册§18](./DELIVERY-HANDOFF.md) 和 [0008](./decisions/0008-live-pet-stream-compat.md)；没有用旧AI覆盖线上。

## 1. 来源与范围

| 项目 | 核实结果 |
| --- | --- |
| 新仓库 | `C:\Users\21203\Desktop\huali-corner-refactor-20261024`，起始 HEAD `c92567d03e988ee2337e75cb8c41a3ce981cd951` |
| 旧 AI 工作区 | `D:\zi\huali-corner-ai`，分支 `ai/borrow-open-source`，HEAD `6edfc13814581c3fdd1b7a241bfe6b3a94a5aa38` |
| 阅读依据 | `AGENTS.md`、AI 接手主文档、decisions 0004/0006、03 规范、交付和验证记录；用户限定第一轮公开 FAQ、可信来源、失败留输入、人工入口 |
| 旧模块 | `ai_service/{server.py,agent.py,rag.py,config.py,ingest.py,knowledge/faq.md,test_agent.py}`；运行时 `index.json` |
| 旧业务接入 | `Backend mission/app/support/{ai.py,service.py}`、`Backend mission/server.py`；Worker 另有 `app/cloudflare/{ai_support.py,ai_knowledge.py}` |
| 改动边界 | 旧工作区只读；按 Git 对象逐文件导入 9 个已跟踪 AI 文件至新仓库，保留原字节，不复制缓存、环境、依赖或用户数据。新增受控服务、合成测试、5 条审核 FAQ 与 provenance |

旧分支与 HEAD 通过 Git 对象命令读取。主任务开始时已经核实旧区 clean；本子任务内的 `git status` 因运行环境的旧盘符工作树访问限制报错，未把失败输出写成新的 clean 证据。没有执行 reset、clean、旧目录编辑或整目录覆盖。

相关提交：

- `6edfc13`：引入 PydanticAI；新增 agent、测试、README 双引擎说明和 `/chat`。
- `8a7338a`：意图体系和购买意图搜索。
- `02a9dce`：知识库去内部文档、兜底和跳转。
- `760999c`：改用外接 DeepSeek API。
- `4eba472`：初始本地 RAG 客服建议。

导入来源及本轮启动合同详见 [ai_service/PROVENANCE.md](../../ai_service/PROVENANCE.md)。旧 README 中供应商价格、模型别名、stars 和上线描述未经本轮外部核验，不作为当前事实或价格建议。

## 2. 旧服务实际合同

旧 `python ai_service/server.py` 启动标准库 `ThreadingHTTPServer`，固定绑定 `127.0.0.1`，默认端口 8093。模块启动时导入 agent，但未安装框架时该模块会降级；无需安装 PydanticAI 即可跑 legacy 摘录。除显式 mock 外，启动检查本地 index 是否存在。

| 入口 | 输入/输出 | 认证与限制 |
| --- | --- | --- |
| GET `/health` | 索引块数、模型名、provider、是否配置 key、index 创建时间；不是模型可用性实测 | 不要求 token；可能暴露内部配置元数据，不适合直接转发浏览器 |
| POST `/reply` | `{question}` → `{answer,action,sources,mode,notice?,latency_ms,support?}`；legacy `rag.answer` | 配置 `HC_AI_TOKEN` 后精确比较服务 Bearer；未配置时匿名允许。JSON 最大64KiB，问题默认最多800字符；额外字段静默忽略 |
| POST `/chat` | `{question,history?}` → agent 结果；有框架/key时含 `answer/action/products/sources/mode='agent'`，错误/降级格式不同 | 同一可选服务 token；历史取最近10条，只保留user/assistant；单条无独立长度限制，仅受总body限制 |
| POST `/reload` | 强制重载 index → `{ok:true}` | 与生成共用可选服务 token；不是后台角色权限校验 |

全部非流式 JSON，没有 SSE。HTTP边界将未处理异常转500，只返回异常类型。日志实现只记方法和去掉query的路径，不记正文；不等于整个模型供应商或其他基础设施都不留存。

`/reply` 的 action 主要为 `reply/transfer/leave_message`，mode为 `rule/guess/mock/llm`；`/chat` 的 action 常为 `none/transfer_human/open_product`。两套枚举和失败语义不同，不能直接作为新前端统一 DTO。

认证分两层：旧业务 `/api/ai/*` 先按原用户 Bearer 核验会话；业务服务调用8093时使用另一个 `HC_AI_TOKEN`。8093自身不认识原用户身份，不能用其可选服务 token 代替新 IdentityPort。

### 2.1 旧业务端并没有自动接到新 agent

- 本地 `server.py` 的 `/api/ai/chat` 读取question，忽略history，调用 `SupportService.ai_chat`。
- 本地 `ai_chat` 和 `ai_reply` 都调用 `support.ai.suggest`，后者固定请求8093的 `/reply`；所以旧业务“chat”名称不等于真正调用 PydanticAI `/chat`。
- 普通聊天问题上限300字符；客服建议从工单主题、正文和最近6条公开回复拼成最多2000字符。内部备注被排除，但工单原文本仍可能含隐私，且2000字符与独立服务默认800字符上限不一致。
- 本地客服建议验证 staff 和 `ticket()` 原权限；Worker客服建议验证staff后直接读取工单主题、正文和6条非internal消息。第一轮不能接这两个含工单数据的路径。
- `support/ai.py` 顶部“不会发到任何云端”的历史注释不符合现状：下一跳虽是回环地址，legacy默认provider仍为外部API。
- `HC_AI_URL` 虽默认回环，但旧 `_url()` 本身不校验远程地址/重定向；agent商品工具的backend配置也未做新架构要求的源站白名单。

### 2.2 PydanticAI 现有缺陷与不可复用的保证

`rag.retrieve` 返回 `[(score,chunk), ...]`；`agent.faq_lookup` 却把每项当dict读取 `.get('question')/.get('answer')/.get('score')`。异常被广泛except吞掉，实际命中也返回空列表。即使改成解包，旧chunk字段也是text/title/source，不是question/answer。

已经用禁网探针复现：同一个“怎么发布闲置”，legacy命中4条tuple，而agent FAQ返回0条。此处在导入旧文件中保持原样，避免来源代码未经说明变更；本轮新服务完全不导入agent。

agent的sources为模型结构化结果的无约束list，可写字符串或其他内容；没有与真实检索结果相交验证。`test_agent.py` 的FAQ假模型即使工具空返回也自行输出来源标题，因此其“来源标注”断言不能证明真实检索或citation可信。

agent注册 `search_products/get_product/faq_lookup/transfer_to_human`；没有实现add_to_cart，工具transfer只返回标记，不代表创建工单或真人已接入。`HC_AI_ENGINE` 只出现在模块说明，没有真实读取分支；有key、框架且非 `HC_AI_MOCK` 时agent不根据 `HC_AI_PROVIDER` 阻止运行。不能把设置provider=mock等同于所有旧入口都不会调用模型。

## 3. 依赖、配置、知识和历史

### 3.1 可复现性与配置名

legacy依赖Python标准库。旧仓库仅跟踪后端 `requirements.txt`（Pillow和pymysql），未跟踪AI的requirements/pyproject/lock；README指导直接 `pip install pydantic-ai`，未锁版本。当前系统Python3.12.5未安装PydanticAI，本轮没有安装或复制旧环境。新项目Python3.13项目环境用于受控服务合成测试，不据此宣称旧PydanticAI兼容性已验收。

| 配置名 | 旧代码用途 |
| --- | --- |
| `HC_AI_PROVIDER`、`HC_AI_MOCK` | legacy选择api/ollama/mock；mock强制摘录 |
| `HC_AI_API_KEY`、`DEEPSEEK_API_KEY` | API密钥主名与兼容名；仅服务端使用 |
| `HC_AI_API_URL`、`HC_AI_MODEL` | 默认DeepSeek OpenAI兼容对话地址及模型名；本文不验证供应商别名有效性 |
| `HC_AI_OLLAMA`、`HC_AI_OLLAMA_MODEL`、`HC_AI_EMBED_MODEL` | 可选本地生成和嵌入模型 |
| `HC_AI_TOP_K`、`HC_AI_MIN_SCORE`、`HC_AI_MAX_QUESTION`、`HC_AI_EMBED` | 检索、问题和嵌入开关 |
| `HC_AI_NUM_CTX`、`HC_AI_NUM_PREDICT`、`HC_AI_TIMEOUT` | 生成预算与网络等待时间 |
| `HC_AI_TOKEN`、`HC_AI_PORT`、`HC_AI_INDEX` | 内部服务认证、端口和索引路径 |
| `HC_AI_BACKEND` | agent商品工具的旧业务地址 |
| `HC_AI_ENABLED`、`HC_AI_URL` | 本地业务是否开放AI、旧独立服务地址 |
| Worker `HC_AI_API_KEY/HC_AI_API_URL/HC_AI_MODEL` | Worker直接调用供应商，绕过本地独立服务 |
| `HC_AI_DAILY_LIMIT` | wrangler变量中有此项，但当前实际配额代码从ai_settings表读取，不应只改该变量就宣称改变额度 |

没有读取或复制任何实际配置key值。旧provider的urlopen保留TLS校验；legacy禁用系统代理但未禁用urllib默认重定向。新内部HTTP adapter应独立拒绝重定向，不扩大原用户凭据的发送范围。

### 3.2 知识库和历史位置

- `ingest.source_files()` 当前只枚举 `ai_service/knowledge/*.md`，不再自动采集运维docs；按标题切片并附id/title/source/text/tokens，可选vector。检索和提示词复用价值较高。
- 旧物理index存在，49块、`embed_ok=false`，唯一source为 `ai_service\knowledge\faq.md`。它被 `.gitignore` 排除，`git ls-files` 中不存在；本轮没有复制或重建它。
- index的id是重建时递增整数，created只是生成时刻；没有发布审批、文档版本、不可变内容摘要、public分类或撤回清单。`HC_AI_INDEX` 可配置任意文件，不能单凭“来源看起来是faq.md”就证明公开发布。
- `/reply.sources` 由检索器 `sources_of` 生成title/source/score，确实不是模型自报；但它列的是所有命中候选，不能证明答案每句都由这些来源支持，也没有稳定document_id/version。
- 旧FAQ存在过时信息，例如“手机四个入口”，与已确认五槽导航冲突；收费/处理时效等也不能整份默认批准。
- Worker知识为生成代码 `app/cloudflare/ai_knowledge.py`，需要单独重建和部署，不是本地index自动同步。Worker检索阈值0.12与legacy关键词最小0.22/向量最小0.28已有差异，不能宣称线上本地完全一致。
- 独立服务本身不持久化聊天全文。agent历史来自客户端；Worker转发最近4条、每条最多300字；本地业务chat不使用history。没有服务端conversation归属验证或历史存储协议。
- 本地 `root/ai-usage.jsonl` 保存actor、时间、渠道、可选ticket_id、来源标题、模式、耗时等；数据库ai_usage保存每用户每日次数和last_at，ai_settings保存开关和限额。不能把“不存聊天全文”误写为完全没有用户关联存储。

## 4. 限流、超时、失败和幂等

| 层 | 当前实际行为 | 缺口 |
| --- | --- | --- |
| 独立server | 无用户配额；ThreadingHTTPServer；legacy生成有全局锁 | 排队等待无总截止，直接访问绕过业务配额 |
| 本地业务 | ai_settings默认普通30/天、staff100/天；距上次记录至少2秒；成功返回后计数，包含摘录/规则答复 | quota检查与计数分离，不能保证并发不超额；失败可能不记数；另有rate_ok函数但未见调用 |
| Worker | 同类数据库配额；仅mode=llm后计数 | 问候/无命中不更新last_at；失败付费或摘录不计，且配额未预留，不能保证并发或实际成本上限 |
| legacy provider | TIMEOUT默认60秒；嵌入固定60秒；无显式自动重试 | HTTP读等待不是完整端到端deadline；全局锁等待另计 |
| 本地业务HTTP | suggest默认等待120秒；reload10秒；不使用系统代理；401转503，其他HTTP错误502，网络失败503 | 超时默认与provider不一致；错误文案可能笼统写服务没启动 |
| agent | 商品HTTP最多20秒；Agent(retries=2)；模型客户端超时/网络重试未显式固定 | 框架结构化校验重试与底层SDK重试都不能当成一次调用保证，版本还未锁定 |
| Worker provider | await workers.fetch，未见显式超时或应用重试 | 不依赖未验证的运行时默认deadline；不能声称完整失败预算已定义 |

legacy模型失败会返回200摘录并附notice，agent模型失败可能返回200转人工字典；这不是新API应统一接受的“回答成功”。旧实现都没有actor+turn_id+request_hash、进行中协调、持久结果或供应商幂等证明，不具备跨重启/超时后的防重复计费保证。

## 5. 第一轮窄接入决定与本轮落地

**结论：保留旧实现，不能把 `/reply` 原样映射为正式公开FAQ API；`/chat` 更不满足本轮范围。** `/reply`可复用的是标准库provider、摘录、文本清洗和检索思路；仅靠包一层response字段适配，不能补齐发布来源、敏感输入、身份和模型失败语义。

采用新受控内部入口 `ai_service/faq_server.py`，不改写旧provider，不引入第二个业务服务writer：

```text
本站 /api/v1/support/assistant/answer
  → IdentityPort：复用组合根的 LegacyGateway，仅 GET /api/me 核实原会话
  → KnowledgePort：只读 approved_faq.json；选出已发布规则与固定版本
  → ModelPort：只发 question + 已批准context + 服务专用HC_AI_TOKEN
  → 127.0.0.1:8093/faq/answer
      → mock摘录 / 现有rag.call_api
  ← answer_text + mock/llm
  ← 本站服务附加KnowledgePort选出的真实sources与人工入口
```

新内部合同：POST `/faq/answer`，只监听回环；`HC_AI_TOKEN`未配时拒绝启动/请求，错误token401。严格仅question/context，均为非空字符串，上限分别800和12000字符；不接受history/user_id/token/任意URL。成功只返回 `{answer_text,mode}`，mode为mock或llm，不提供来源或任何业务操作。未知provider503，模型异常/空回答502，绝不自动重试或把模型失败伪装为成功摘录。显式mock及未配置key时为摘录。TLS沿用旧provider验证，没有放宽。

`approved_faq.json` 的documents仅5条：模拟付款、同卖家合并送货费、三至九张实拍图及三个角度、创建30分钟付款时限、普通用户在线客服工单前置。每项固定document_id/title/version/content/source；version为 `2026-10-24-c92567d`。规则分别对照当前新仓库 `trade/service.py`、`catalog/service.py`、`community/service.py`，没有把全部旧FAQ承诺当成已审核政策。30分钟关闭明确由超时任务执行，不承诺墙钟一到瞬时关闭。

外层职责不能漏接：

- 原Bearer只发本站和IdentityPort的已配置身份源；由 `/api/me` 核实身份后仅保留可信actor标识，不把完整个人资料传给模型。身份超时返回503，不能冒充401使前端清会话。
- 用户在问题里粘贴token、密码、恢复码等也属于待处理输入；应在发模型前按服务端策略拒绝或拦截，不能仅靠prompt“不要输出”。第一轮不接受私密上下文、订单号上下文拉取、附件或持久聊天。
- sources由KnowledgePort映射，不接受模型citation、任意URL或模型自报置信度；未知规则说明无法确认并给人工入口。
- 人工下一步仅 `/support/new`。用户明确检查并提交后才由旧唯一writer创建工单；不声称AI已转接，不自动建单、退款、订单动作或客服认领。
- ModelPort地址须配置回环白名单、拒绝跳转、限制响应和等待时间；不把AI加入现有COMPAT_PATHS任意代理。
- 同账号同turn同question可重用已完成结果；不同question原turn拒绝，账号隔离；取消/超时结果未知时不自动发第二个付费请求。进程内去重不能宣称持久防重复计费。
- 页面用纯文本显示，失败保留输入；离开页面/切换账号取消并丢弃迟到结果；登录状态401与模型/身份503分开处理。

## 6. 本轮执行证据与未验收项

1. 只读Git日志/对象、源码和JSON元数据；导入9个已跟踪文件，未复制index、.venv、node_modules、数据库、日志或凭据。旧区不变。
2. Python3.12.5、`-B`禁pycache的只读探针，封死urllib外部网络、mock且两种key为空：legacy检索4条tuple，agentFAQ为0；legacy摘录成功，来源字段为title/source/score。这证明现有检索合同缺陷，不证明真实模型质量。
3. 旧PydanticAI测试未运行：当前未安装该框架，且无依赖锁。旧Cloudflare测试的受限环境尝试未取得完整结果后中止，不能写成通过。
4. 新测试先执行，因缺少faq_server模块失败；新增实现后，沙盒回环HTTP遭WinError10013。经自动审批允许在隔离外执行相同合成测试，9项真实回环HTTP测试通过，约0.7秒；所有供应商urllib请求被测试阻断，仅使用合成provider返回或异常。没有以mock冒充真实模型调用。
5. 最后复核：9项HTTP测试全部通过（0.687秒）；新增服务及测试Ruff check通过、format --check显示2文件已格式化，限定范围git diff --check通过。再次从旧Git对象逐字节比较9个导入文件全部一致，并断言新目录不存在index缓存。未全目录格式化或给历史函数批量加注释。

复现受控服务测试命令（项目根）：

```powershell
& apps/api/.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s ai_service -p test_faq_server.py -v
& apps/api/.venv/Scripts/python.exe -m ruff check ai_service/faq_server.py ai_service/test_faq_server.py --config apps/api/pyproject.toml --no-cache
& apps/api/.venv/Scripts/python.exe -m ruff format --check ai_service/faq_server.py ai_service/test_faq_server.py --config apps/api/pyproject.toml --no-cache
```

未验收：真实DeepSeek/Ollama可用性及内容质量、供应商留存与授权范围、真实Worker/D1/R2、生产负载和发布切流、跨进程持久幂等、旧PydanticAI修复、全部旧FAQ政策审核。第一轮来源审批和合成链路成功不改变整站business_ready=false，也不等于已允许生产部署。
