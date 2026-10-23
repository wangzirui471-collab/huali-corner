# 本机开源模型跑客服（DeepSeek-R1-Distill-Qwen）

> 目标：客服问答全流程走**本机开源模型**——知识库检索在本机、生成也在本机，
> 客户问题一个字都不出这台电脑。
> 适用：客户资料敏感、不想外传、想长期自己掌控（不按 token 付费）。
> 不适用：几十人同时在线的高并发（见第 5 节）。

相关代码：`ai_service/llm.py`（模型网关）、`ai_service/rag.py`（检索 + 规则）、
`ai_service/server.py`（127.0.0.1:8093）、`ai_service/preflight.py`（自检）。

---

## 1. 先说清楚：RAG 不需要蒸馏

| 想做的事 | 需要什么 | 不需要 |
| --- | --- | --- |
| 让 AI 按你的 FAQ/商品文档回答 | 检索（RAG）+ 一个通用小模型 | 蒸馏、微调 |
| 让模型记住你家的口径、语气 | 改知识库、改提示词 | 训练 |
| 做一个"客服专用小模型"卖给别人 | 这才需要蒸馏 / SFT | — |

`DeepSeek-R1-Distill-Qwen-7B` 是 DeepSeek 开源放出的**权重**（MIT），
Ollama 里的 `deepseek-r1:7b` 就是它，默认按 **Q4_K_M** 量化，约 4.7GB。
8G 显存能装下，代价是并发差、长回答慢。

---

## 2. 硬件对照

| 显存 | 自动选型 | 权重占用 | 单次回答（250–300 字） | 结论 |
| --- | --- | --- | --- | --- |
| 8G（RTX 4060 笔记本） | `deepseek-r1:7b` | ≈4.7GB | 10–20 秒 | 够 1–2 位客服，试用/小流量正合适 |
| 12G+ | `deepseek-r1:14b` | ≈9GB | 15–30 秒 | 质量更好，仍然串行 |
| 4–6G | `deepseek-r1:1.5b` | ≈1.1GB | 3–6 秒 | 快但笨，只适合 FAQ 直答 |
| 没独显 | 同上，CPU 跑 | — | 每秒 2–4 字 | 只能演示，别拿去接客户 |

启动脚本会读 `nvidia-smi` 自动选档（`HC_AI_AUTO_MODEL=1`，默认开）。
显存探不到就沿用 `HC_AI_OLLAMA_MODEL`，不会瞎降档。

---

## 3. 一次性安装（Windows）

```powershell
# 1) 装 Ollama（装完它会常驻托盘）
#    https://ollama.com/download

# 2) 拉模型（一次性，约 4.7GB）
ollama pull deepseek-r1:7b

# 3) 生成知识库索引（只改了 FAQ 才需要重跑）
cd "E:\zi\huali-corner-trial"
.\.venv-trial\Scripts\python.exe ai_service\ingest.py

# 4) 自检：能不能跑、跑多大、大概多慢，一条命令看清
.\.venv-trial\Scripts\python.exe ai_service\preflight.py --ask "怎么发布商品"
```

自检输出长这样（本机没显卡时的真实输出）：

```
  [OK] Python     3.12.7
  [!]  显卡       没检测到 NVIDIA 显卡 / 没装驱动
  [x]  Ollama     连不上 http://127.0.0.1:11434
  [OK] 知识库索引  49 条切片 · 关键词检索
  [OK] 并发设置   并发 1 · 排队上限 3 · 常驻 30m
  结论：现在只能跑「知识库摘录」，上面标 [x] 的先按提示处理。
```

---

## 4. 启动与验证

双击根目录 **`启动AI-本地模型.bat`**（它做四件事：查 Ollama → 查/拉模型 →
补索引 → 自检后启动并预热模型）。等价的手动方式：

```powershell
$env:HC_AI_PROVIDER="ollama"
$env:HC_AI_AUTO_MODEL="1"
.\.venv-trial\Scripts\python.exe ai_service\server.py
```

另开一个窗口跑后端：`start-trial-8081.bat`。

验证：

```powershell
# 模型就绪 / 加载状态 / 显存 / 排队
curl http://127.0.0.1:8093/health
# {"provider":"ollama","model":"deepseek-r1:7b","local":true,"model_ready":true,
#  "model_loaded":true,"vram_gb":8.0,"concurrency":1,...}

# 问一句
curl -X POST http://127.0.0.1:8093/reply -H "Content-Type: application/json" `
  -d '{\"question\":\"怎么发布商品\"}'
# mode=llm 表示真的是本机模型答的；mode=mock 表示降级成了知识库摘录
```

网页上：`#support` → 右下角小转。此时面板底部提示会变成
「模型跑在本机，问题不会离开这台电脑」——这句话由 `/api/config` 的
`ai_local` 字段驱动，不是写死的。

**模型没起也照样能开工**：服务自动降级成知识库原文摘录，页面顶部标注原因，
不会白屏、不会 500。

---

## 5. 容量：老实说只能扛 1–2 人

串行（默认并发 1）下，7B Q4 在 4060 上约 30–40 token/s，一次 300 字回答
≈ 450 token ≈ 12–18 秒，加上提示词处理约 **10–20 秒/次**。
也就是说这台机器**每分钟最多 3–5 次问答**。

| 同时提问的客服 | 实际体验 |
| --- | --- |
| 1 人 | 10–20 秒出答案，可接受 |
| 2 人 | 第二个人等 20–40 秒，勉强 |
| 5 人 | 第三人开始排 1 分钟以上，会以为坏了 |
| 10+ 人 | 别硬扛，换方案 |

超过 2 人时的选项（按性价比排序）：

1. **混合路由**（推荐）：客户问答走本机，L1 办公助手/批量草稿走云端（见第 7 节）。
2. **换小模型**：`deepseek-r1:1.5b` 快 3–4 倍，但复杂问题会答得敷衍。
3. **上更大显卡**：24G 跑 14b，快不了多少，是质量提升不是并发提升。
4. **vLLM / llama.cpp 批处理**：`HC_AI_PROVIDER=openai_local` 指向自建端点，
   靠 continuous batching 提升吞吐——但 8G 显存依旧装不下更大 batch。

代码里为此设了三道闸，不是让你去调参硬扛：

- `HC_AI_MAX_CONCURRENCY=1`：默认串行，避免两个请求互相把显存挤爆；
- `HC_AI_QUEUE=3` + `HC_AI_QUEUE_TIMEOUT=45`：排满 45 秒还没轮到，
  直接回「现在人多，先按原文答你」，**不会让客户盯着转圈到超时**；
- 排队时前端会显示「排队中 · 摘录」，客服知道这不是坏了。

---

## 6. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `HC_AI_PROVIDER` | `api` | `ollama`（= `local`）/ `openai_local` / `api` / `mock` |
| `HC_AI_OLLAMA` | `http://127.0.0.1:11434` | Ollama 地址 |
| `HC_AI_OLLAMA_MODEL` | `deepseek-r1:7b` | 固定档位（关掉自动选型时才用） |
| `HC_AI_AUTO_MODEL` | `1` | 按显存自动选 14b / 7b / 1.5b |
| `HC_AI_KEEP_ALIVE` | `30m` | 模型常驻时长；设 0 会每次冷加载 |
| `HC_AI_MAX_CONCURRENCY` | `1` | 同时跑几个请求；8G 显存别调大 |
| `HC_AI_QUEUE` / `HC_AI_QUEUE_TIMEOUT` | `3` / `45` | 排队上限与最长等待（秒） |
| `HC_AI_LOCAL_URL` | `http://127.0.0.1:8080/v1/chat/completions` | 自建 OpenAI 兼容端点 |
| `HC_AI_LOCAL_MODEL` | 空 | 自建端点的模型名 |
| `HC_AI_LOCAL_MAX_PREDICT` | `700` | 本地模型输出上限；给太大只会拖到超时 |
| `HC_AI_WARMUP` | `1` | 启动时预加载模型 |
| `HC_AI_OWNER_PROVIDER` | 空 | L1 办公助手单独走后端（见下） |

`HC_AI_API_KEY` 仍然用于远端 API；切到 `ollama` 后**不需要任何 Key**。

---

## 7. 混合路由：客户走本机，办公走云端

小显卡扛得住一问一答，扛不住「一次生成 20 条工单回复」。可以只把 L1 的
办公助手切到云端，客户问答继续留在本机：

```powershell
$env:HC_AI_PROVIDER="ollama"          # 客户问答：本机 7B
$env:HC_AI_OWNER_PROVIDER="api"       # L1 办公草稿：云端
$env:HC_AI_API_KEY="sk-..."
$env:HC_AI_MODEL_OWNER="deepseek-flash"
```

此时客户的问题不出本机，只有 L1 主动发起的批量草稿走 API。

---

## 8. 故障对照表

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `/health` 的 `provider` 还是 `api` | 环境变量没生效 | 在**启动 AI 服务的那个窗口**设置，然后重启服务 |
| `连不上 Ollama` | 没装 / 没启动 / 被代理拦了 | 打开 Ollama 托盘；代码已强制绕过系统代理 |
| `model_ready: false` + `ollama pull ...` | 模型没下载 | 按 hint 里的命令拉，或重跑启动脚本 |
| 首个问题要等 10 秒以上 | 模型被换出显存 | 保持 `HC_AI_KEEP_ALIVE=30m`；别同时开游戏/剪辑软件 |
| 回答里出现"让我想想…"然后没了 | 输出被 `num_predict` 截断 | 已按「半截推理=没答案」处理并退回原文；可调高 `HC_AI_LOCAL_MAX_PREDICT` |
| 回答慢到 30 秒+ | 显存不够发生 CPU 卸载，或并发 >1 | 降档到 1.5b；`HC_AI_MAX_CONCURRENCY=1` |
| 页面提示"排队中 · 摘录" | 同时在问的人超过闸门 | 正常保护，不是故障；10–20 秒后重问 |
| 答得不如线上 API | 7B 量化模型能力上限 | 正常。知识库写细一点，把判断交给规则，模型只负责组织语言 |

---

## 9. 隐私边界怎么变了

| | 外接 API（`HC_AI_PROVIDER=api`） | 本机模型（`ollama`） |
| --- | --- | --- |
| 客户问题去哪 | 发到 DeepSeek 服务器 | 不出本机 |
| 面板提示 | "问题会发送给第三方 AI 服务" | "模型跑在本机，问题不会离开这台电脑" |
| `<ai_local>` 字段 | `false` | `true`（由 `/health` 的 `local` 推出） |
| 费用 | 按 token 计费 | 只有电费 |
| 日志 | `var-trial/ai-usage.jsonl` 只记元数据 | 同左，仍然不记问题与回答全文 |

注意：本机模式解决的是"数据不出机器"，**不解决**合规备案、公网访问、
内容审核——对外运营仍然需要自己处理这些。

---

## 10. 和线上 Cloudflare 的关系

```
本地试用：浏览器 → 后端 8081 → ai_service 8093 → 本机 Ollama（本文档）
线上：    浏览器 → Worker → D1/R2 + DeepSeek API（app/cloudflare/ai_support.py）
```

Workers 运行时（Pyodide）没有 GPU、没有线程，**跑不了开源权重模型**，
所以线上只能走 API 或在你自己的服务器上跑本文档这套再反代。
两边的规则、词表、提示词是两份副本，改规则要一起改（见 `docs/CONTEXT-2026-10-22.md` 第 3 节）。

本地 AI 服务与 Worker 的接口形状保持一致（`/reply` 返回
`{answer, action, sources, mode, notice}`），所以前端不需要知道后面是谁在答。
