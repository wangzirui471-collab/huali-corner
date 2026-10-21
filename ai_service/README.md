# 转角 AI 客服（知识库 + 外接 DeepSeek API）

给客服页的 AI 宠物和工单页的「AI 建议回复」提供回答：先检索本地知识库，再调用 **DeepSeek 官方 API** 生成，只允许依据资料回答，不确定就转人工。

默认模型：**`deepseek-flash`**（DeepSeek-V4.1-Flash-1017，官方最便宜的档）。
- 官方文档：<https://api-docs.deepseek.com/>
- Base URL：`https://api.deepseek.com`，对话接口：`/chat/completions`
- 价格（人民币/百万 tokens）：空闲时段输入 1 元、输出 4 元；高峰时段输入 2 元、输出 8 元（以官方页面为准）
- 高峰时段：北京时间周一至周五 9:00—12:00、14:00—18:00；其余为空闲时段

## 它怎么工作

```
客服页宠物 / 工单页 AI 建议
        │
        ▼
本地后端 /api/ai/chat 或 /api/ai/reply
        │
        ▼
ai_service（127.0.0.1:8093）
  1. 意图判断：问候 → 短回复；转人工/投诉 → 直接转接
  2. 业务问题 → 检索 index.json（关键词或向量）
  3. 命中资料 → 只把【资料 + 问题】发给 DeepSeek
  4. 资料不足/模型不确定 → 固定兜底话术「马上帮您转接人工客服」
        │
        ▼
DeepSeek API
        │
        ▼
返回 {answer, action, sources, mode}
```

**为什么先做「建议」而不是自动回复**：AI 回答由客服确认后插入回复框，不直接发给客户；退款、投诉、账号安全仍然转人工。

## 本地怎么用

1. 去 <https://platform.deepseek.com/> 创建 API Key。
2. 设置环境变量（PowerShell，当前窗口有效）：

```powershell
$env:HC_AI_API_KEY="sk-你的Key"
$env:HC_AI_MODEL="deepseek-flash"
```

3. 生成知识库索引（不需要 Ollama，默认关键词检索）：

```powershell
cd "E:\zi\huali-corner-trial"
python ai_service\ingest.py
```

4. 启动 AI 服务：

```powershell
python ai_service\server.py
```

看到 `AI 客服已启动` 即可；`/health` 会显示 `provider=api`、`model=deepseek-flash`、`api_configured=true`。

5. 启动/重启后端：

```powershell
start-trial-8081.bat
```

6. 打开 `http://127.0.0.1:8081/#support`，点右下角宠物；客服账号在工单页还能看到「AI 建议回复」。

## 线上 Cloudflare

Worker 里同一套检索/兜底逻辑在 `app/cloudflare/ai_support.py`，知识库打包在 `ai_knowledge.py`。

```powershell
cd "E:\zi\huali-corner-trial\Backend mission"

# 只设置一次；Key 不要写进仓库、文档或聊天
node "C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules\wrangler\bin\wrangler.js" secret put HC_AI_API_KEY

# 部署 Worker（模型名/接口地址已在 wrangler.jsonc 的 vars 里）
node "C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules\wrangler\bin\wrangler.js" deploy
```

- 设置 Key 之前，`/api/config` 的 `ai` 为 false，客服页不显示宠物；设置后自动出现。
- 线上额度：每账号每天 30 次、两次提问至少间隔 2 秒（D1 `ai_usage` 表），避免 Key 被刷。
- 知识库更新：改 `ai_service/knowledge/faq.md` → 重跑 `python ai_service/ingest.py` → 重新生成 `ai_knowledge.py`（见下）→ 重新部署。

## 没有 Key / 想省钱时

- 不设置 `HC_AI_API_KEY`：自动退化为**知识库摘录**，页面会标注「未配置 DeepSeek API Key」，不产生费用。
- 强制摘录：`$env:HC_AI_MOCK="1"`。
- 想用本地模型：`$env:HC_AI_PROVIDER="ollama"; $env:HC_AI_OLLAMA_MODEL="deepseek-r1:7b"`，需要本机 Ollama。

## 配置项

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `HC_AI_PROVIDER` | `api` | `api` / `ollama` / `mock` |
| `HC_AI_API_KEY` | 空 | DeepSeek Key；也可用 `DEEPSEEK_API_KEY` |
| `HC_AI_API_URL` | `https://api.deepseek.com/chat/completions` | OpenAI 兼容接口 |
| `HC_AI_MODEL` | `deepseek-flash` | 官方最便宜档；旧名 `deepseek-v4-flash` 也接受 |
| `HC_AI_MOCK` | `0` | `1` = 只摘录，不调 API |
| `HC_AI_TOP_K` | `4` | 检索条数 |
| `HC_AI_MIN_SCORE` | `0.12` | 低于该分数直接转人工 |
| `HC_AI_PORT` | `8093` | 本地服务端口 |
| `HC_AI_TOKEN` | 空 | 可选，设置后后端需带同一个 token |
| `HC_AI_ENABLED` | 本地默认开 | 后端是否暴露 `/api/ai/*` |

## 知识库同步到 Worker

本地 `ai_service/index.json` 是主索引；Worker 用 `app/cloudflare/ai_knowledge.py`。改完 FAQ 后执行：

```powershell
python ai_service\ingest.py
python - <<"PY"
import json
from pathlib import Path
idx=json.loads(Path("ai_service/index.json").read_text(encoding="utf-8"))
chunks=[{"title":c["title"],"source":c["source"],"text":c["text"]} for c in idx["chunks"]]
lines=["# 自动生成，勿手改。","KNOWLEDGE = ["]
lines += ["    "+repr(c)+"," for c in chunks]
lines += ["]"]
Path("Backend mission/app/cloudflare/ai_knowledge.py").write_text("\n".join(lines)+"\n",encoding="utf-8")
print("chunks",len(chunks))
PY
```

## 隐私与边界

- **问题会发送到 DeepSeek API**（这是外接方案与本地模型的区别）；不要发送密码、恢复码、完整手机号、他人聊天记录等敏感信息。
- 内部备注不进入提示词；工单只取主题、用户描述和公开对话。
- 后端只写 `var-trial/ai-usage.jsonl`：时间、操作人、渠道、来源标题、耗时、模式；不写问题与回答全文。
- 公开对外使用仍受服务器、公网访问、备案和合规限制；正式运营前需在隐私说明中写明「使用第三方大模型服务」。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `AI 未配置` / 一直摘录 | 没设 `HC_AI_API_KEY`；设置后重启 AI 服务 |
| 401 / 403 | Key 无效或余额不足；去 DeepSeek 控制台检查 |
| 429 | 用户当天 30 次用完，或两次提问间隔 <2 秒 |
| 回答带推理过程 | 已剥离 ` thinking`；仍出现可换 `HC_AI_MODEL=deepseek-v4-pro` 或联系服务商 |
| 总是转人工 | 知识库没覆盖；补 FAQ 后重跑 ingest / 重新生成 ai_knowledge.py |
| 费用超预期 | 检查 `ai-usage.jsonl` 的调用量；降低每日额度或改成 `HC_AI_MOCK=1` |
