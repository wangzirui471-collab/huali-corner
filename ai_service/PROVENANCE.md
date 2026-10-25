# AI 模块来源与本轮受控入口

旧来源工作区：`D:\zi\huali-corner-ai`，分支 `ai/borrow-open-source`，提交 `6edfc13814581c3fdd1b7a241bfe6b3a94a5aa38`。

本目录的 `.gitignore`、`README.md`、`agent.py`、`config.py`、`ingest.py`、`knowledge/faq.md`、`rag.py`、`server.py`、`test_agent.py` 从该提交 Git 对象逐文件按原始字节导入。旧工作区没有改动；未复制 `index.json`、依赖、虚拟环境、数据库、日志、凭据或用户数据。导入旧 README 是保留历史来源，其供应商价格、模型别名和已上线措辞未经本轮外部核验，不作为当前部署承诺。

本轮新增 `faq_server.py`、`test_faq_server.py`、`approved_faq.json` 与本文。新 FastAPI 只允许使用 `faq_server.py` 的受控端点；旧 `server.py` 的 `/reply`、`/chat`、`/reload` 仍保留供历史实现审查，不是本轮客户端入口。`agent.py` 的检索合同缺陷保持原样登记，未为复用而悄悄修改来源代码。

## 当前内部合同

- 只绑定 `127.0.0.1`，端口由 `HC_AI_PORT` 指定，默认 8093。
- `POST /faq/answer`；必须配置 `HC_AI_TOKEN`，请求认证为服务专用 `Authorization: Bearer <HC_AI_TOKEN>`。这不是用户原 Bearer；用户 token 不得离开本站身份适配边界。
- 严格正文 `{"question":"非空问题，最多800字","context":"本站选出的公开资料，最多12000字"}`；任何额外字段（history、user_id、token 等）均拒绝。
- 成功 `{"answer_text":"纯文本","mode":"mock或llm"}`，无伪造 citation、订单、工单或自动转接动作；provider 配置值仍为 `api`。
- 本站 KnowledgePort 只读 `approved_faq.json` 的 `documents`，每项固定 `document_id/title/version/content/source`。这些版本指向新仓库基线 c92567d 的代码审核；不得把旧全部 FAQ 或旧缓存直接替换进去。
- `HC_AI_PROVIDER=mock` 强制仅摘录；默认 `api` 在无 key 时亦仅摘录。已配置 `api` 时直接复用 `rag.call_api`，不自动重试；模型异常或空回答为 502。其他 provider 在该入口拒绝。
- api 所需配置名仍为 `HC_AI_API_KEY`（兼容 `DEEPSEEK_API_KEY`）、`HC_AI_API_URL`、`HC_AI_MODEL`、`HC_AI_TIMEOUT`、`HC_AI_NUM_PREDICT`。不复制已有环境值。TLS 验证沿用原 provider，未放宽。
- 不依赖 PydanticAI、不读取 index、不开放商品工具或历史，不新增业务 writer。外层 API 负责认证、敏感输入拒绝、限流、去重与将可信来源附加到 Envelope。

## 合成启动和验证

从项目根使用现有项目 Python；本轮验证只使用 mock，不调用模型供应商：

```powershell
$env:HC_AI_PROVIDER = 'mock'
$env:HC_AI_TOKEN = '<为本次本机服务单独生成的令牌>'
& apps/api/.venv/Scripts/python.exe -B ai_service/faq_server.py
```

另一个终端运行合成测试：

```powershell
& apps/api/.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s ai_service -p test_faq_server.py -v
```

测试只连接本机随机回环端口，并阻断供应商 urllib 网络调用。`test_agent.py` 属于保留的历史测试，需要额外 PydanticAI，未纳入本轮受控端点的依赖或通过声明。
