# 线上原AI的增量流适配

此目录属于既有 support/assistant 的兼容入口。新增 `POST /api/ai/chat/stream`，原 `/api/ai/chat` 及其余AI、办公、商品与售后路径继续原线上实现。没有引入数据库迁移或另一套业务writer，也没有第三方宠物项目。

候选必须从线上版本 `5e7bd074-0fe4-42ba-887a-2f5347a7479e` 的原字节快照生成，不能使用本地旧后端替代。构建验证全部218项原manifest摘要，只修改 `worker.py` 和 `app/cloudflare/ai_support.py`，新增两个流模块，其余216模块原字节保留。原备份不写入。

```powershell
apps/api/.venv/Scripts/python.exe infra/cloudflare/pet-stream/stage_stream.py --snapshot .local-config/live-worker-5e7bd074 --target artifacts/pet-stream-stage
apps/api/.venv/Scripts/python.exe -m unittest discover -s infra/cloudflare/pet-stream/tests -v
apps/api/.venv/Scripts/python.exe -m ruff check infra/cloudflare/pet-stream
apps/api/.venv/Scripts/python.exe -m ruff format --check infra/cloudflare/pet-stream
```

候选存在时使用 `--refresh`：先验证候选全部登记摘要，再只刷新四个模块和清单，保留根任务的本机配置。摘要漂移时停止。产物、快照和本机配置均不入Git。运行环境中的Windows asyncio若在沙盒挂起，应使用获准的本机执行；不修改系统事件循环或TLS设置。

## 协议与身份

请求严格只接受 `question`（非空且最多300字）、`history`（最多4条，每条仅user/assistant角色与最多300字content）、`client_turn_id`（UUID）。不新增 order_id 或客户端提供的私有上下文。复用原 `page_user`、`ai_enabled`、`ai_quota` 与原 `ai_answer`；原业务仍决定规则答复、知识、商品、售后资料与权限。鉴权与输入错误在开始流前返回原JSON错误；流中故障返回脱敏error事件。

事件依次为 `turn {client_turn_id}`、零条或多条 `delta {text}`、恰好一个成功终态 `done {client_turn_id,result}`，或者失败终态 `error {code,message}`。断连时不再补发终态。`result` 是原 `ai_chat` 的完整DTO；原摘录、长度裁剪、安全过滤可能修正增量正文，因此客户端应以done中的answer替换预览，并保留support、sources、links、action等元数据。

## 真实流与取消

仅在当前请求的ContextVar里设置hook，原 `call_api` 没有hook时继续原逻辑。流模型仍使用原 `HC_AI_API_KEY`、`HC_AI_API_URL`、`HC_AI_MODEL`、原提示词、history、温度与token上限，唯一供应商协议变化为 `stream:true`。逐块读取ReadableStream reader并解析 `choices[0].delta.content`；不读取完整响应text后模拟打字。忽略 `reasoning_content`，跨块隐藏 `<think...>...</think>` 与thinking/reasoning代码围栏；完整结束标记缺失、空公开正文及供应商错误均不报成功。

浏览器取消同时触发AbortController、取消Python业务任务、关闭reader并释放锁。65秒整体超时亦失败关闭；不自动重试供应商。错误不会包含上游响应、密钥、堆栈或原请求全文。JS回调代理在流关闭或取消后释放，避免长驻Worker积累闭包。FFI写法依据[Cloudflare官方Streams Python示例](https://developers.cloudflare.com/workers/runtime-apis/streams/)；实际workerd验收另由根任务记录。

增量出口同样复用原 `guard_leak` 和其强弱指纹。潜在指纹前缀、第一处弱指纹、未闭合JSON及编码串先缓冲；命中原提示词泄漏判定的片段不会通过delta提前暴露，最终仍由原DTO完成安全替换。正常中文正文逐块放行，少数可疑片段可能等到结束才放行；这不改变供应商真实流式读取。

## 额度与重放限制

流路径通过原quota校验后登记原 `ai_count`，在首个模型请求开始前预留一次额度，原结尾跳过已预留计数，避免双算。纯规则答不扣。模型已开始的取消、供应商失败和结果未知均保留已预留额度，不冒称已退款；这保证停止不能直接绕过模型额度。旧非流路径保留原来的成功后计数规则。

没有新增持久轮次表，也没有跨进程去重保证。UUID用于关联事件，不表示服务端已实现幂等；客户端须保留已完成轮次并禁止自动重发。原quota检查与计数之间的并发竞态沿用原writer能力，不能宣称已实现原子全局额度或绝不重复计费。

## 测试边界与回退

测试覆盖逐字节UTF8/SSE、第一块实时可见、思考跨块、reasoning忽略、EOF/空正文/错误、取消、ContextVar隔离、原ai_chat完整DTO/原后处理、原model配置、额度一次、规则免扣与旧JSON非流回归。平台I/O使用合成reader与会话，不连接收费模型、真实数据库、R2或线上Worker，不能当作真实D1/R2验收。

回退为恢复备份中的两个旧模块并移除两个新增模块，或者恢复原线上版本；没有数据迁移。已预留的AI次数保持记录，不能以回退为由擅自改真实额度。部署、绑定和逐模块最终SHA核对由根任务负责。

## 本轮发布工具

`node infra/cloudflare/pet-stream/release-worker.cjs plan` 仅本机校验并生成清单。`upload` 使用Wrangler已有OAuth，仅向固定Cloudflare官方API上传新版本，不切流；`activate` 必须已有候选只读验收且当前原部署未变化。secret采用strict inherit，不读取模型密钥值，所有回执均无认证秘密。正式版本及129资源/220模块实测结果见交付手册§18。无需安装额外依赖。

回退命令为同脚本的 `rollback`，先核对当前部署仍是本轮版本，再恢复原5e7bd074；未实际执行生产回退演练。此工具只适用于本轮固定Worker、备份和版本，不能拿作其他项目的通用部署脚本。换机先保全忽略目录中的原备份与无秘密回执，禁止用较旧本地后端重新构建替代线上AI。
