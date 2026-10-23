# L1 工单办公交付说明（2026-10-23）

## 本轮解决的问题

基线为 `feature/ai-perf` / `feature/ai-support-rag` 的 `b70d0de8acb1a1e6a081ec9b2188024d5ff6c598`。
截图中的办公助手只把 `_office_stats()` 汇总放入提示词，没有读取工单或处理工单的工具，
因此无法列明细，也无法落实“全部处理”。本轮补齐工单工具，保留原账号确认动作。

现在从小转「办公 → 待处理工单 / 工单办公」，或输入“全部处理”“查看工单 #编号”，
可以读取真实授权工单、查看公开补充、生成逐单草稿、修改动作和依据，再预览并确认执行。
本轮不含数字商品发布，也不代表整站重构或完整通用 Agent 已完成。

## 真实执行范围

| 动作 | 实际效果 |
| --- | --- |
| 仅回复 | 公开回复、相关用户通知及处理依据审计，不改工单状态 |
| 受理并回复 | 状态转处理中、指派当前所有者、公开回复、通知、审计 |
| 提交复核并回复 | 状态转复核、公开回复、通知、审计 |
| 回复并结案 | 只对无关联订单的一般反馈/改约开放；复用现有结案通知和会话归档 |

退款、举报、申诉不允许从该批量入口结案、退款或处罚。自涉工单、涉及本人商品或订单的工单，
以及已经由其他客服受理的工单，只显示说明和工作台入口。受理不等于已解决。
列表默认包括历史积压，不能把“二十四小时”统计当作所有待办的时间范围。

## 已复用的开源组件

- **Vue 3.5.44 + Element Plus 2.14.7**：对话框、表单、选择框、提示和焦点管理。
  源码在 `office-ui/`，通过 Vite 8.3.5 构建。普通首屏不导入该包，只有 L1 打开工单工具时加载。
  构建后的 JS/CSS 与开源许可位于 `web 7M/assets/office/`。
- **LangGraph 1.2.16**：独立 Python AI 服务中的真实 `StateGraph`，运行
  “校验公开资料 → 模型起草 → 校验预览”三个步骤。输入输出范围由适配层限制，
  它没有平台数据库、登录会话或写入工具。没有把 LangGraph 塞进 Pyodide Worker。
- 工单写入复用原 `StaffApi.cf_staff_reply_plan` / `cf_staff_resolve_plan`；
  没有复制一套退款、通知、结案逻辑，也没有新建独立业务 writer。

本轮 LangGraph **没有**使用持久化 checkpointer 或 `interrupt()`；不能把它描述为已完成的
持久化通用 Agent。这里的人工作业快照属于平台确认协议，与已有账号动作确认一样，
由后端校验并原子执行。后续通用 Agent 的长期任务、工具规划和断点恢复可以继续采用开源框架。

官方资料：[LangGraph](https://github.com/langchain-ai/langgraph)、
[中断与持久化要求](https://docs.langchain.com/oss/python/langgraph/interrupts)、
[Element Plus](https://github.com/element-plus/element-plus)、[Vue](https://github.com/vuejs/core)。
Pydantic AI 的 [Deferred Tools](https://ai.pydantic.dev/deferred-tools/) 也经过比较，本轮没有引入。

## 工具协议与权限

以下均为 POST，沿用现有 Bearer 登录态，后端要求有效且 active 的 owner：

| 路由 | 输入与结果 |
| --- | --- |
| `/api/ai/office` | 原问题协议兼容；工单问题直接返回 `office_tool=tickets` 和明细，不依赖模型猜测 |
| `/api/ai/office/tickets/list` | `page`、`status`、可选 `ticket_id`；返回分页、总量、权限原因、公开补充及 revision |
| `/api/ai/office/tickets/draft` | `ticket_ids`、以编号为键的 `revisions`；返回逐单草稿，尚未发送 |
| `/api/ai/office/tickets/prepare` | `items[{id,revision,action,body,reason}]`；保存十分钟内有效的确认快照 |
| `/api/ai/office/tickets/confirm` | 只接受 `proposal_id` 和 `confirmed:true`；不能替换正文或动作 |

公开正文会做联系方式/链接/密钥脱敏；内部备注不进入助手或外部模型。角色、归属、
工单状态、关联订单和公开/内部消息游标都会影响可处理性或快照。
生成草稿前、保存预览前以及执行时都要核对当前版本；出现新消息需要刷新明细重新阅读。

执行前再次检查 active owner、利益冲突和全部快照，检查语句全部先于业务写入。
工单更新、公开回复、通知、领域审计、批次审计与完成回执在**同一个 D1 batch**里提交。
任何审计失败都会整批回滚；同一预览重试只返回已经提交的回执。
新表 `ai_office_jobs` 同步加入 SQLite/MySQL schema 与 D1 备份清单。

## D1 查询预算

官方限制为每条查询最多 100 个绑定参数；每次 Worker 调用 Free 最多 50 次查询，
Paid 最多 1000 次。见 [D1 limits](https://developers.cloudflare.com/d1/platform/limits/)。

本轮已把每张工单的守卫拆为同一个 batch 内的独立语句，避免四条工单起就超参数限制。
**默认 `HC_OFFICE_BATCH_LIMIT=1`**，列表、草稿、准备、确认统一逐单，兼容保守的 Free 预算。
只有运维核实当前环境的查询预算后，才设置该变量为 2–20；二十条批量验收使用明确配置的
合成 Paid 预算，不能当作 Free 环境已经支持二十条。界面明确显示总量、每批上限与下一页。
没有新增收费资源，也没有修改现有套餐。

## 可选 LangGraph 草稿服务

在独立 Python 3.12 环境安装并启动（本轮验证版本）：

```powershell
python -m pip install -r ai_service/requirements-office.txt
# 使用服务端安全配置注入 HC_AI_TOKEN；不要写入源码、命令历史或公开文档。
python ai_service/server.py
```

服务仍默认绑定 `127.0.0.1:8093`。办公草稿端点是 `/office/tickets/draft`，必须配置 `HC_AI_TOKEN`。
Worker 访问独立服务时，用运维配置的 `HC_OFFICE_AGENT_URL`（HTTPS 基址）和独立 secret
`HC_OFFICE_AGENT_TOKEN`，两端令牌对应。没有替用户搭建公网代理或部署该服务。
跨网络服务的 TLS 校验保持开启，不放行 HTTP 来绕过证书问题。

模型继续使用 OpenAI 兼容接口；独立服务可用 `HC_AI_MODEL_OWNER`、`HC_AI_API_URL_OWNER`、
`HC_AI_API_KEY_OWNER` 单独配置所有者模型或已有自托管推理端点。普通客服仍用原配置。
没有 GPU 集群部署、模型权重下载或真实模型调用验收；这不是完成 V3/R1 自托管。

未配置 LangGraph 服务时，工单查询和人工处理仍可用；草稿沿用 Worker 模型调用。
模型/外部服务不可用时返回明确标注的基础受理草稿，不会假装已经解决工单。

## 上线前步骤与回退

首次实现阶段未执行部署。随后用户明确授权三方同步，已同步实际本地 E 项目与 GitHub AI 分支，
仅在当前绑定 D1 新增空确认表并成功发布 Worker。原 Postman 等待提交内容已保存并保留；
未执行真实账号修改或生产客户工单处理。完整实际结果及后续边界见交付手册与验证记录。
以下步骤作为后续发布参考。

1. 核对要合入的真实工作区与当前分支，保留现有未提交修改；对本切片做代码审阅。
2. 确认数据库权威源和备份后，审阅 `Backend mission/migrations/20261023_ai_office_jobs.sql`。
   该迁移只新增确认表；真实执行需要单独安排，不能使用旧 `remote:true` 配置做本地验证。
3. `npm ci` 后在 `office-ui/` 执行 `npm run build`，Worker 和同次静态资源一起发布。
   已提交构建资源便于审阅，不能只发布旧 JS 搭配新接口。
4. 可选配置独立草稿服务与经核实的批次上限；先用合成账号在真实隔离平台验收。
5. 验收 owner/非 owner、过期、重复提交、新消息、审计失败、订单关联和手机操作。

回退应用时恢复此前已知良好版本；确认表可暂时保留，旧版本不会读取它，
不要通过删表抹掉已执行回执或审计。正式保留期限与任务记录清理纳入后续运维策略。

## 后续顺序

1. 本切片的真实隔离 Worker/D1/R2、模型端点与发布验收。
2. 数字商品：用户已明确指电子资料/模板等正式商品；采用预览、确认、发布、数字交付完整切片。
   本轮没有实现、没有上架商品；初步测试草稿保留在当前工作区仓库外，未混入已通过测试。
3. 在开源 Agent 框架上逐步补充多轮工具规划、长期任务、断点恢复、文件办公和工作流模板，
   每轮一个可验收切片，不以“引用框架”替代实际接入。

## 正式 Worker 图片依赖（2026-10-23）

不能直接复用原 `python_modules` 中的 Pillow 12.2.0，也不能把 Windows wheel 放进 Worker。
已用官方 Pyodide 配方 `314-20260911`，将 Pillow 源码版本与官方 PyPI SHA256 固定到 12.3.0；
通过 GitHub Ubuntu 隔离编译，目标是 CPython 3.14 / pyemscripten_2026_0_wasm32。
没有自行实现图片库、重命名旧版本或放宽 TLS/KDF。

[实际成功构建](https://github.com/wangzirui471-collab/huali-corner/actions/runs/39906746810)
在真实 Pyodide 314.0.7 验证版本、JPEG/PNG/WebP、EXIF 校正/去元数据、坏图拒绝和像素上限。
本轮 wheel SHA256 为 `315cf03364146407d03d96c59da49a88b4b86e55ec6ee3e5075d64eb037ef51c`，
完整来源和制品摘要见 `Backend mission/worker-pillow.lock.json`。

下载该运行的 `huali-pillow-12.3.0-wasm` 制品，先核对 GitHub artifact digest，再解压到私密目录。
使用干净的独立发布目录运行 `scripts/install_worker_pillow.py --wheel <wheel路径> --proof <运行证明JSON路径>`。
安装器核对当前发布锁、版本、ABI、运行证明、Wasm 标头和 ZIP 路径，拒绝覆盖现有目录；
`--check-only` 可只检查。校验即使 Python 开启优化也不会被跳过。
已存在的旧目录须先另存到项目 `_local/` 或工作区私密备份位置，不能删掉原文件后碰运气。

制品默认保留十四天，过期后可重跑固定配方的工作流；新产物应重新校验并更新锁，不能盲用新摘要。
Wrangler 直连发布显式使用 `disable_python_external_sdk`，继续使用平台内置 SDK，
保持兼容日期 2026-10-17；未来改用完整 pywrangler 外置 SDK 应作为独立平台验收。
上面的 Wasm 包验收不替代实际 Worker 发布校验或真实账号业务验收。
