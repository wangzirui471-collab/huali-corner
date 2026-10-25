# 公开 FAQ 智能客服实施计划

> 执行者使用 executing-plans 或 subagent-driven-development，按任务逐项验证，用户明确的本轮接管要求为范围依据。

**目标：** 在已核对交付版本上接通公开 FAQ，复用已有 AI 服务，保留唯一 writer。

**架构：** AssistantService 组合身份、审核知识和模型端口；bootstrap 装配。Vue 按 feature 提交单轮问答，显式注入旧会话，人工操作继续走现有工单。

**技术：** Python 3.13/FastAPI、JavaScript/Vue 3/Element Plus，已有纯 Python rag 服务，无新增供应商 SDK。

**规格：** 用户本轮请求、AI-TAKEOVER-AND-INTEGRATION.md、decisions/0007-public-faq-assistant.md。

## 约束与复审重点

- 所有新增函数、测试和任务入口中文 docstring/JSDoc；仅修改本切片，不覆盖旧目录。
- 不连接真实库，不用 remote:true，不部署、不收费、不降低 TLS/KDF。
- 防止身份服务故障误清会话、凭据进入模型、伪造来源、并发重复调用以及账号切换迟到响应。

## 任务

- [x] 同步远端 c92567d 到全新独立副本，记录旧脏文件与 AI SHA；核对远端 CI 实际状态。
- [x] 基线：项目锁定依赖安装，原提交API30项、当前API53项、前端57项、旧业务483项与11个旧客户端脚本分别复跑；远端CI失败与未知根因如实保留。
- [x] 服务端：先失败合同测试，再实现 modules/support/assistant/{ports,schema,rules,service,api}.py 与 infrastructure/assistant.py；bootstrap 注入同一 LegacyGateway。
- [x] AI：从明确提交按文件保留 ai_service，新增认证 FAQ 专用入口及审核清单，不复制依赖、缓存或凭据；内部HTTP9项通过。
- [x] 前端：features/support/assistant 中实现协议与生命周期、原键重试、纯文本来源、失败留输入及人工草稿；SupportPage 最小接线。
- [x] 集成：真实回环登录/问答、四宽度浏览器、HTML失败重试和仅人工草稿检查通过；OpenAPI与声明已生成。
- [x] 独立复审、修复坏HTTP映射/成功重提原键/Host代理问题，更新交付与验证记录；保留生产、Worker及真实模型未验范围。
