# 转角 AI 客服（本地 RAG）

给客服工单页提供「AI 建议回复」：先检索本地知识库，再让 DeepSeek 开源模型**只依据资料**生成回答。数据不出本机，不需要训练/蒸馏。

## 它怎么工作

```
客服点「AI 建议回复」
        │
        ▼
本地后端 /api/ai/reply（校验客服权限、取工单上下文）
        │
        ▼
ai_service（127.0.0.1:8093）
  1. 意图判断：问候 → 直接短回复；转人工/投诉 → 直接转接
  2. 业务问题 → 检索 index.json（向量或关键词）
  3. 命中资料 → 只把【资料 + 问题】交给 DeepSeek
  4. 资料不足/模型不确定 → 固定兜底话术「马上帮您转接人工客服」
        │
        ▼
返回 {answer, action, sources, mode}
        │
        ▼
客服看到建议 + 来源，确认后插入回复框（不会自动发给客户）
```

**为什么先做「建议」而不是自动回复**：8G 显卡跑 7B 量化只能承受 1—2 个并发，自动回复一旦胡说或卡住，客户直接流失；人工确认一步，既保留效率又可控。等准确率稳定后，再把 `action=reply` 且高置信度的回答接成自动发送。

## 硬件与模型

| 项目 | 建议 |
| --- | --- |
| 显卡 | RTX 4060 Laptop 8G（你的 R7000） |
| 模型 | `deepseek-r1:7b`（Ollama 的 Q4 量化，约 4.7GB） |
| 向量模型 | `nomic-embed-text`（约 274MB） |
| 上下文 | `num_ctx=4096`，`num_predict=360` |
| 并发 | 1—2 个客服同时用；更多会排队/变慢 |
| 备选 | 显存不够时用 `deepseek-r1:1.5b`；想更快可换 `qwen2.5:7b` |

不需要蒸馏：RAG 是「检索 + 提示」，不训练模型。只有要做专属小模型时才需要蒸馏。

## 一次性安装

1. 安装 Ollama（Windows）：<https://ollama.com/download>
2. 拉模型（第一次会下载几 GB）：

```powershell
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
```

3. 生成知识库索引：

```powershell
cd "E:\zi\huali-corner-trial"
python ai_service\ingest.py
```

看到 `embed: on` 表示向量检索已启用；如果 Ollama 没起，会自动退化为关键词检索，仍然能跑。

4. 启动 AI 服务（保持窗口开着）：

```powershell
python ai_service\server.py
```

5. 自测：

```powershell
Invoke-RestMethod http://127.0.0.1:8093/health
Invoke-RestMethod http://127.0.0.1:8093/reply -Method Post -ContentType "application/json" -Body '{"question":"怎么发布闲置？"}'
```

6. 重启后端（`start-trial-8081.bat`），打开客服工作台 → 任意工单 → 「AI 建议回复」。

## 没有 GPU / 模型没下好时

先用摘录模式把链路跑通（不调用模型，只摘录最相关的知识库原文）：

```powershell
$env:HC_AI_MOCK="1"
python ai_service\server.py
```

返回里 `mode=mock`，前端会标注「当前未连接生成模型，以下为知识库原文摘录」。

## 知识库怎么更新

- 面向客户的规则写在 `ai_service/knowledge/faq.md`；`docs/TRIAL.md`、`docs/PUBLIC-ACCESS.md`、`docs/SUPPORT_CONTEXT-2026-10-20.md` 也会被收录。
- 改完后重新跑 `python ai_service\ingest.py`；服务不用重启，调一次 `POST /reload` 或重启也行。
- **不要**把内部部署、分支、凭据、学生名单放进知识库。

## 配置项

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `HC_AI_OLLAMA` | `http://127.0.0.1:11434` | Ollama 地址 |
| `HC_AI_MODEL` | `deepseek-r1:7b` | 生成模型 |
| `HC_AI_EMBED_MODEL` | `nomic-embed-text` | 向量模型 |
| `HC_AI_MOCK` | `0` | `1` = 不调模型，只摘录 |
| `HC_AI_TOP_K` | `4` | 检索条数 |
| `HC_AI_MIN_SCORE` | `0.12` | 低于该分数直接转人工 |
| `HC_AI_PORT` | `8093` | 本地服务端口 |
| `HC_AI_TOKEN` | 空 | 可选，设置后后端需带同一个 token |
| `HC_AI_ENABLED` | 本地默认开 | 后端是否暴露 `/api/ai/reply` |

## 隐私与边界

- AI 服务只绑定 `127.0.0.1`，工单内容只在本机内存里处理，不发给任何云端 API。
- 后端只在 `ai-usage.jsonl` 记录「工单号、命中来源、耗时、模式」，不记录客户原话和 AI 回答全文。
- 内部备注不会发给 AI；只取工单主题、用户描述和公开对话。
- 这是一个**辅助工具**：不自动发给客户、不替客服做退款/处罚决定、不承诺优惠或赔付。
- 公开对外使用仍受服务器、公网访问、备案和合规限制；当前只建议在本地试用/内部客服使用。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `AI 服务未启动` | 先运行 `python ai_service\server.py`；确认 8093 没被占用 |
| 生成很慢 | 7B 在 8G 显卡上首轮要加载模型；关掉游戏/浏览器占显存；把 `num_ctx` 降到 2048 |
| 显存不足 | 换 `deepseek-r1:1.5b` 或 `qwen2.5:3b`，重新设 `HC_AI_MODEL` |
| 总是转人工 | 知识库没有覆盖该问题，补 FAQ 后重跑 ingest；或临时调低 `HC_AI_MIN_SCORE` |
| 回答带推理过程 | 已在 `rag.py` 里剥离 ` thinking`；若仍出现，换非 R1 的 `qwen2.5:7b` |
