# 工作模式（Owner Work Mode）

> 2026-10-23 新增。给 L1 所有者用的「平台工具台」：用一句话查全平台数据，或让 Agent
> 选工具完成操作；不可逆动作必须二次确认。不是给普通客服/用户的功能。

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
| `content_remove` | 危险 | 移除帖子 / 评论 |
| `demo_cleanup` | 危险 | 删除全部 `virtual` 演示商品 |
| `backup` | 写 | 打包数据库与上传文件到 `backups/` |
| `notification_send` | 写 | 给指定账号发站内通知 |
| `ai_settings` | 危险 | 开关 AI、调整每日额度 |
| `demo_publish` | 写 | 批量入库演示商品（virtual） |

当前共 **35 个工具**（16 读 + 19 写）。新增工具只需在 `app/support/work.py` 的 `TOOLS` 注册，并实现 `READ` 或 `_execute` 分支。

## 3. 接口

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/ai/work/tools` | GET | 工具目录（owner） |
| `/api/ai/work/chat` | POST | `{question}`：Agent 选工具并返回结果/待确认卡 |
| `/api/ai/work/call` | POST | `{tool,args,token?}`：直接调工具；写工具不带 token 返回 proposal |
| `/api/ai/work/confirm` | POST | `{token}`：执行已确认的写操作 |

所有接口都走 `SupportService` 的 owner 校验；写操作执行后写 `ai_office_*` / `ai_work_*` 审计。

## 4. Agent 流程

```
用户一句话
  → 先认账号动作（降级/注销/下线）→ 直接出 proposal
  → 否则让 AI 规划器选工具（ai_service /plan，输出 {"tool","args"}）
        · 规划器只能从工具目录里选，不能编造
        · 模型不可用/超时 → 退回关键词规则路由
  → 执行读工具，返回 answer + items + tool
  → 写工具只返回 proposal + 一次性 token（10 分钟有效）
  → owner 在浏览器二次确认 → /api/ai/work/confirm → 执行 + 审计
```

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
- 写工具永不自动执行；token 与 owner 绑定、10 分钟过期、HMAC 防篡改。
- 当前工作模式只做**单步工具**；多步任务（先搜商品再下架）需要分两次对话，或后续加多步规划。
- 线上 Cloudflare 目前只有「办公」接口；工作模式先落本地，D1 版工具需要另行移植。

## 7. 测试

```powershell
cd E:\zi\huali-corner-trial\tests
..\.venv-trial\Scripts\python.exe -m unittest test_owner_office test_work_mode -v
```

覆盖：工具目录、概览/用户/工单/趋势/会话/治理/信誉/账本查询、写操作 proposal→confirm、
owner 保护、非 owner 403、无效 token、Agent 动作路由、封禁与注销语义区分。
