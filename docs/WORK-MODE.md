# 工作模式（Owner Work Mode）

> 2026-10-23 新增。给 L1 所有者用的「平台工具台」：用一句话查全平台数据，或让 Agent
> 选工具完成操作；不可逆动作必须二次确认。不是给普通客服/用户的功能。
>
> 本地与 Cloudflare D1 **同一套契约**（`/api/ai/work/*` 四个接口、同一份工具目录），
> 数据层不同：本地 SQLite + HMAC 令牌；线上 D1 + `ai_office_jobs` 提案表。
> 实现：本地 `app/support/work.py`，线上 `app/cloudflare/work_mode.py`。

## 1. 定位

- **只对 owner（L1）开放**：`/api/ai/work/*` 全部 owner-only，非 owner 一律 403。
- **读工具直接执行**：确定性 SQL，不把用户名单/手机号交给模型“编”。
- **写工具只出 proposal**：后端生成一次性 token，owner 在浏览器确认后才执行；模型永远不直接写库。
- **全量数据**：用户、商品、订单、工单、审计、趋势；默认手机号打码，`reveal=true` 才看全号并写 `pii_view` 审计。

## 2. 工具目录

| 工具 | 风险 | 能做什么 |
| --- | --- | --- |
| `overview` | 读 | 用户/商品/订单/工单总量、24h 活跃 |
| `users` | 读 | 按昵称/手机号/角色/状态查账号 |
| `user_detail` | 读 | 资料 + 商品/订单/工单数量 + 最近商品 |
| `products` | 读 | 按标题/分类/状态/卖家查商品 |
| `product_detail` | 读 | 商品 + 卖家 + 相关订单 |
| `orders` | 读 | 按状态/买卖家/天数查订单 |
| `order_detail` | 读 | 订单条目 + 双方 + 金额 |
| `tickets` | 读 | 按状态/类型/关键词查工单 |
| `ticket_detail` | 读 | 工单 + 全部对话（含内部备注） |
| `audit` | 读 | 按操作人/类型/天数查审计 |
| `stats` | 读 | 最近 N 天订单/工单趋势 + 活跃用户总数 |
| `rooms` | 读 | 群聊/私聊/客服会话，含最近消息与受理人 |
| `messages` | 读 | 指定会话最近消息（写 `chat_view` 审计） |
| `moderation` | 读 | 待处理举报、被移除帖子/评论、待审商品 |
| `credit` | 读 | 低信誉用户 + 最近信誉变动 |
| `offers` | 读 | 最近出价/还价记录 |
| `posts` | 读 | 按关键词搜帖子/评论 |
| `ledger` | 读 | 按类型汇总流水 + 最近记录 |
| `sellers` | 读 | 最近 N 天成交额/单量排行 |
| `user_role` | 危险 | 调整 user/support/admin/developer（不能动 owner） |
| `user_disable` | 危险 | 注销账号、下架在售、撤销会话 |
| `user_revoke` | 写 | 强制下线 |
| `product_moderate` | 危险 | 平台下架 / 恢复上架 |
| `ticket_reply` | 写 | 工单公开回复 / 内部备注 |
| `ticket_resolve` | 危险 | 认领 / 复核 / 退款 / 驳回 / 结案 |
| `user_ban` | 危险 | 封禁 / 解封账号（含在途订单处置） |
| `user_credit` | 危险 | 基于已结案工单调整信誉分 |
| `product_promote` | 写 | 平台置顶 1/3/7 天（模拟支付） |
| `product_batch_delist` | 危险 | 整店下架某卖家全部在售商品 |
| `product_bulk_moderate` | 危险 | 按关键词/分类/卖家批量下架或恢复（最多 50 件） |
| `content_remove` | 危险 | 移除帖子 / 评论 |
| `demo_cleanup` | 危险 | 删除全部 `virtual` 演示商品 |
| `backup` | 写 | 打包数据库与上传文件到 `backups/` |
| `notification_send` | 写 | 给指定账号发站内通知 |
| `ai_settings` | 危险 | 开关 AI、调整每日额度 |
| `demo_generate` | 读 | 按主题生成演示商品预览（不写库），确认后用 `demo_publish` 入库 |
| `demo_publish` | 写 | 批量入库演示商品（virtual） |

当前共 **37 个工具**（20 读 + 17 写）。新增工具只需在 `app/support/work.py` 与
`app/cloudflare/work_mode.py` 的 `TOOLS` 注册，并实现 `READ` 或 `_execute` 分支
（线上是 `_read_*` / `_work_plan_statements`）。两处目录保持一致，规划器才能
在本地和线上给出同一套行为。

差异说明：线上 `content_remove` 只支持 `post` / `message`（D1 评论表没有
`removed` 列，移除评论请移除整帖或到管理台处理）；其余工具语义一致。

## 3. 接口

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/ai/work/tools` | GET | 工具目录（owner） |
| `/api/ai/work/chat` | POST | `{question}`：Agent 选工具并返回结果/待确认卡 |
| `/api/ai/work/call` | POST | `{tool,args,token?}`：直接调工具；写工具不带 token 返回 proposal |
| `/api/ai/work/confirm` | POST | `{token}`：执行已确认的写操作 |

所有接口都走 owner 校验（本地 `SupportService.is_owner`，线上 `cf_staff_actor`）；
写操作执行后写 `ai_office_*` / `ai_work_*` 审计。

## 4. Agent 流程

```
用户一句话
  → 先认账号动作（降级/注销/封禁/下线）→ 直接出 proposal
  → 否则进入 ReAct 循环（最多 3 步）：
      1. /plan：问题 + 工具目录 + 已执行步骤摘要 → {"tool","args"} 或 {"tool":"final"}
      2. 执行读工具，结果摘要回填 observations
      3. 规划器决定下一步（可能从「查商品」衔接到「批量下架」）
      4. 写工具只返回 proposal + 一次性 token（10 分钟）
  → 模型不可用/超时 → 退回关键词规则路由
  → owner 在浏览器二次确认 → /api/ai/work/confirm → 执行 + 审计
```

示例：「把卖假货的商品全部下架」
`products(q=假货)` → 看到候选 → `product_bulk_moderate(q=假货, action=delist)` → 确认卡。

示例：「发布 3 件宿舍好物演示商品」
`demo_generate(prompt=宿舍好物, count=3)` → 预览（不写库）→ `demo_publish` → 确认卡 → 入库。
预览项由后端从上一步结果直接传入，不经模型转抄（模型抄不动 5 件商品的结构化字段）。

规划器提示词要求「待办→tickets、订单→orders、用户→users、商品→products」，
只有宽泛的“平台怎么样”才选 overview。

## 5. 前端入口

小转面板（客服页右下角）→ 页签 **工作**（仅 owner 可见）：

- 快捷：平台概览 / 待处理工单 / 查用户 / 查订单 / 查商品 / 看审计 / 趋势
- 自由输入：如「帮我看看最近 7 天有哪些订单」「把 godfly 降为客服」
- 写操作会显示红色「待执行」卡，点「确认执行」后浏览器再 confirm 一次
- 结果下方会标注实际调用的工具名，便于排查

## 6. 隐私与边界

- 默认手机号打码；查看全号需要 `reveal=true`，并写 `pii_view` 审计。
- 工具参数/结果不写进模型上下文（读工具由代码直接拼答案）；只有规划阶段把**问题**和**工具目录**发给模型，不发业务数据。
- 写工具永不自动执行；本地 token 与 owner 绑定、10 分钟过期、HMAC 防篡改；
  线上提案写 `ai_office_jobs`（随机作业号、绑定 actor、10 分钟过期），确认时
  在**同一个 D1 batch** 里复查 owner 身份、作业状态与参数，再执行业务写入。
- 「生成预览 → 确认入库」：`demo_generate` 只出预览（不写库），预览项由后端
  直接传给 `demo_publish`，不经模型转抄；owner 点确认后才批量入库。
- 线上已部署：Cloudflare 与本地同一套接口；规划器用 `HC_AI_MODEL_OWNER`
  指定更强模型，未配 `HC_AI_API_KEY` 时自动退回关键词规则路由。

## 7. 测试

```powershell
cd E:\zi\huali-corner-trial
# 本地（SQLite）
.venv-trial\Scripts\python.exe -m unittest tests.test_work_mode tests.test_owner_office -v
# 线上同构（内存 D1）
.venv-trial\Scripts\python.exe -m unittest tests.test_cloudflare_work_mode -v
# 评测集（golden set）
.venv-trial\Scripts\python.exe tests\eval_work_agent.py
```

覆盖：工具目录、概览/用户/工单/趋势/会话/治理/信誉/账本查询、写操作 proposal→confirm、
owner 保护、非 owner 403、无效/过期/他人 token、Agent 动作路由、封禁与注销语义区分、
多步「查询→批量下架」、批量操作不落库、「生成预览→确认入库」闭环。
评测集 9/9；线上同构测试 24 项。
