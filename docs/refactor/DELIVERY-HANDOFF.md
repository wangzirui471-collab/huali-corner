# AI 分支补充交付（2026-10-23）

本文件是 `feature/ai-perf` 的本轮补充，不是旧重构交付手册的替代版本。
此 AI 分支基线 `b70d0de8acb1a1e6a081ec9b2188024d5ff6c598` 未包含原 `e611c310...`
分支的 `AGENTS.md`、`apps/web`、`apps/api` 或旧 `docs/refactor` 设计文档。
已从指定交付提交读取开发约定，未把两个分支自动合并或回退到重构前基线。

## 实际进度

- 已核对 GitHub 两条 AI 分支的基线，owner 和办公查询/账号确认动作已存在。
- 已修复截图暴露的工单汇总无法落到具体工作的缺口：真实明细、逐单草稿、人工确认、
  复用工作台处理计划的原子执行、回执、防重复和旧快照拦截。
- 新增 JavaScript + Vue 3 + Element Plus 的按需加载工单面板。
- 真实接入可选独立 LangGraph 草稿编排服务；未在 Worker 中强装其本地二进制依赖。
- T00–T03 及整站重构没有在本轮完成；数字商品发布、自托管 GPU 和通用 Agent 长任务仍未完成。

## 接手入口

完整功能、协议、配置、D1 预算、迁移与回退步骤见 [AI-OFFICE.md](../AI-OFFICE.md)。
实际执行的验证见 [verification.md](verification.md)。
旧项目位置、业务说明仍见 [CONTEXT-2026-10-22.md](../CONTEXT-2026-10-22.md)，
其中旧线上版本及分支信息不能当作本轮已重新部署的证据。

## 修改重点

- `Backend mission/app/cloudflare/office_tickets.py`：L1 工单工具与确认协议。
- `Backend mission/app/cloudflare/staff_api.py`：提取现有业务计划，工作台与助手共用。
- `Backend mission/app/cloudflare/d1.py`：可组合的事务守卫，兼容单条查询参数上限。
- `office-ui/`、`web 7M/assets/office/`：前端源码、锁文件和构建资源。
- `ai_service/office_agent.py`、`requirements-office*`：开源 LangGraph 接入及锁定依赖。
- `Backend mission/migrations/20261023_ai_office_jobs.sql`：仅新增确认表的待审迁移。

## 运行与边界

后端继续承载现有业务；新增工具没有独立数据库 writer。办公工单接口本轮接入的是
线上使用的 Worker API；旧本地业务 `server.py` 并未新增同名办公 API，不能宣称三端均已同步。
本地 AI 服务只负责可选草稿编排，不等于本地业务 API 已实现办公工单工具。

默认逐单；核实 Paid 查询预算后可配置 `HC_OFFICE_BATCH_LIMIT`，最多二十条。
真实数据库权威源仍需运维确认，迁移和部署尚未执行。

## 后续顺序

先审阅本切片并完成真实隔离平台验收与受控发布，再推进数字商品完整发布/交付切片。
保留真实工作区未提交修改、Postman 测试、旧账号和原有业务；禁止 `reset --hard`、`git clean`
或自动合并多库。保持 TLS、KDF、Pillow 正式依赖和品牌要求。

## 三方同步整合预检（2026-10-23）

用户随后授权本地项目、GitHub、Cloudflare 三方同步。核实实际本地目录为
`E:\zi\huali-corner-trial`，两条 AI 远端分支已更新到 `7fd4e15`。
本轮将该已提交成果合入独立交付分支，保留只读用户/订单/商品/审计查询、售后选单、演示商品及面板功能。

原目录已有的 `office_data.py` 概览修复、查询回归、快捷按钮换行和用户/订单入口经核验纳入；
复现并修复 `KeyError: today`，不虚构数据库未提供的用户新增统计。
未提交 Postman/工作流修改、随后新增的导购和尺寸调整均保留，不自动打包成已验收发布功能。
同步本地时须先保存原工作区快照，再快进并保留这些待提交修改，禁止整目录覆盖。

同时修复上游 `global:true` 请求跳过账号隔离的问题：全局请求仅豁免路由变化，
换号始终拒绝迟到响应；同页退出/登录立即清理小转内容、上下文和待执行预览，并卸载工单面板。

整合预检：后端 562 项、前端 11 个检查脚本、实际构建及四个浏览器场景通过。
Worker `deploy --dry-run --keep-vars` 已通过；真实部署与表结构操作以发布回执为准。
读取当前线上回退版本 `6f58a0e8-81c1-447a-973c-753b433764ac`，并取得绑定库的 Time Travel 恢复书签。
全库导出被自动审批拒绝，未执行，未改用其他方式下载真实业务记录。
