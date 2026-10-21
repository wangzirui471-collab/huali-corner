# AI 客服（本地 RAG）设计与边界

> 2026-10-21 新增。给客服工单页提供「AI 建议回复」：本地知识库检索 + 外接 DeepSeek API 生成（默认 `deepseek-flash`，官方最便宜档）。
> 部署与命令见 [`ai_service/README.md`](../ai_service/README.md)。

## 1. 产品定位

**是**：客服工作台里的辅助工具。客服点「生成建议」，AI 基于知识库给一段可直接发送的草稿和来源；客服核对后手动插入回复框。

**不是**：

- 不是自动回复机器人——不会替客服直接发给客户；
- 不是退款/处罚决策工具——不承诺优惠、赔付、封号结果；
- 不是本地模型——默认调用 DeepSeek 官方 API，问题文本会发送到 DeepSeek；敏感信息不要输入。

**为什么先做“建议”**：RTX4060 8G 跑 7B 量化只能承受 1—2 个并发；自动回复一旦胡说或卡住，客户直接流失。人工确认一步，既保留效率又可控。等准确率稳定、并发需求明确后，再把高置信度的 `action=reply` 接成自动发送。

## 2. 行为规范（企业客服 Agent 流程）

1. **意图判断**：问候/闲聊 → 简短问候，不检索；明确说“转人工/找客服/人工” → 直接转接；投诉、差评、强烈不满 → 直接转接。
2. **业务问题** → 检索本地知识库，取最相关的 4 条。
3. **只依据资料回答**：资料没写的，不许用模型自带知识补全；不承诺优惠、质保、赔偿、发货时效；不用“大概、可能、应该是”等不确定表述。
4. **资料不足/检索为空** → 固定兜底话术，一字不差：
   > 这个问题我暂时无法为您准确解答，马上帮您转接人工客服。
5. **不输出思维链**：R1 的 ` thinking`、推理段落、Markdown 标题都会被剥离；回答控制在 300 字内。
6. **隐私**：内部备注不进入提示词；只取工单主题、用户描述和公开对话。

## 2.1 客服页宠物入口

客服页（`#support`，非客服工作台）右下角有一只 AI 宠物：

- 待机动画：用户提供的 8×12 雪碧图第一行 8 帧，已抠成透明底 `assets/ai-pet/idle-strip.png`；
- 点击宠物 → 打开「转角 AI 小助手」对话面板；
- 快捷问题：怎么发布 / 怎么退款 / 客服时间 / 注销账号；
- 普通登录用户即可使用，走 `POST /api/ai/chat`（不需要客服权限）；
- 命中资料 → 正常回答；资料不足/投诉/要求人工 → 固定兜底 + 「提交工单」按钮；
- 同一账号两次提问至少间隔 2 秒，避免连点刷模型；
- 线上 Cloudflare `config.ai` 为假，宠物不渲染。

## 3. 架构

```
客服工单页（staff 角色 + config.ai）
        │  点击「生成建议」
        ▼
POST /api/ai/reply  {ticket_id}
  后端 SupportService.ai_reply：
    - 校验 support/admin/developer
    - 读取工单（不含 internal 备注）
    - 调用本地 ai_service
        │
        ▼
ai_service（127.0.0.1:8093）
    classify -> retrieve（index.json） -> prompt -> DeepSeek /chat/completions
        │
        ▼
{answer, action, sources, mode, notice, latency_ms}
        │
        ▼
客服看到草稿 + 来源；「插入回复框」→ 人工核对 → 发送
```

## 4. 关键文件

| 文件 | 作用 |
| --- | --- |
| `ai_service/rag.py` | 意图判断、检索、提示词、生成、兜底与剥离思考 |
| `ai_service/ingest.py` | 知识库切片与索引（向量或关键词） |
| `ai_service/server.py` | 本地 HTTP 服务（只绑 127.0.0.1） |
| `ai_service/knowledge/faq.md` | 面向客户的规则知识库 |
| `Backend mission/app/support/ai.py` | 后端到 AI 服务的客户端（绕过系统代理） |
| `Backend mission/app/support/service.py` | `ai_reply`：权限、工单上下文、`ai-usage.jsonl` |
| `web 7M/src/pages/support.js` | 工单页 AI 面板（仅客服 + `config.ai`） |
| `web 7M/src/components/ai-pet.js` | 客服页悬浮宠物 + 对话面板 |
| `web 7M/ai-pet.css` | 宠物动画、面板与消息样式 |
| `web 7M/assets/ai-pet/` | 待机雪碧条与宠物头像 |
| `POST /api/ai/chat` | 客户侧 AI 小助手（登录用户、限速） |
| `web 7M/src/actions/support.js` | 生成、插入回复框、错误提示 |
| `web 7M/ai-support.css` | 面板样式 |
| `Backend mission/app/cloudflare/ai_support.py` | Worker 侧检索 + 外接 API + 每日额度 |
| `Backend mission/app/cloudflare/ai_knowledge.py` | 打包进 Worker 的知识库（自动生成） |

## 5. 配置与开关

- 本地 `server.py` 的 `/api/config` 返回 `ai: true`（`HC_AI_ENABLED=1`，默认开）。
- Cloudflare 的 `ai` = 是否设置了 `HC_AI_API_KEY` 密钥；未设置时宠物/按钮不显示。
- 本地 AI 服务地址：`HC_AI_URL`，默认 `http://127.0.0.1:8093`。
- 模型：`HC_AI_MODEL=deepseek-flash`（DeepSeek-V4.1-Flash，官方最便宜档）；
  接口 `HC_AI_API_URL=https://api.deepseek.com/chat/completions`。
- Key：本地 `HC_AI_API_KEY`；线上 `wrangler secret put HC_AI_API_KEY`。
- 没有 Key 时自动退化为知识库摘录，`mode=mock`，前端标注原因。
- 线上额度：每账号每天 30 次、两次提问至少间隔 2 秒（D1 `ai_usage`）。

## 6. 隐私与日志

- 本地 AI 服务只绑定回环地址；但生成阶段会把【命中的资料 + 问题】发送到 DeepSeek API。
- 不要输入密码、恢复码、完整手机号、他人聊天记录等敏感信息；内部备注不进入提示词。
- 后端只写 `var-trial/ai-usage.jsonl`：时间、操作人、工单号、action、mode、来源标题、耗时；**不写客户原话和回答全文**。
- 内部备注不发 AI；管理端聊天审计规则不变。
- 知识库里不要放：真实手机号、聊天原文、学生名单、部署凭据。

## 7. 验收

| 编号 | 场景 | 通过标准 |
| --- | --- | --- |
| AI-01 | 客服权限 | support/admin/developer 可调用；普通用户 403 |
| AI-02 | 命中知识库 | 「怎么发布闲置」返回发布规则 + 来源；action=reply |
| AI-03 | 未命中 | 「可以便宜点吗」返回固定兜底话术；action=transfer |
| AI-04 | 投诉/转人工 | 「我要投诉」直接转接，不检索 |
| AI-05 | 无模型降级 | `HC_AI_MOCK=1` 时返回知识库摘录，并标注原因 |
| AI-06 | 不自动发送 | 生成后只填充回复框；不调用 `/ticket/reply` |
| AI-07 | 隐私 | `ai-usage.jsonl` 不含客户原话/回答全文；内部备注不进入提示词 |
| AI-08 | 线上隐藏 | Cloudflare 环境 `config.ai` 为假，工单页无 AI 面板 |
| AI-09 | 宠物入口 | 客服页右下角宠物可见；点击打开对话；快捷问题有回答；兜底时「提交工单」可打开工单弹窗 |
| AI-10 | 外接 API | 设置 Key 后 `mode=llm`；未设置时自动摘录并标注；401/额度 429 有可读提示 |

## 8. 局限与下一步

- 依赖 DeepSeek API 可用性与余额；Key 失效时自动退回知识库摘录。
- 成本：按 token 计费，线上每账号每天 30 次上限；可在 `ai-usage.jsonl` 观察调用量。
- 知识库需要人工维护；规则改了要重跑 `ingest.py` 并重新生成 Worker 的 `ai_knowledge.py`。
- 下一步（按优先级）：
  1. 客服对 AI 草稿点「有用/没用」，积累评测集；
  2. 高置信度 + 常见问题（发布/退款/面交/客服时间）开放自动回复；
  3. 知识库后台：运营在网页上编辑 FAQ，保存后自动重建索引；
  4. 多轮上下文：把同一工单最近 3 轮对话带进检索与生成。
