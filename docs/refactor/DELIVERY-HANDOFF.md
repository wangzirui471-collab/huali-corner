# AI 分支补充交付（2026-10-23）

## 最新交付结果

已按用户明确授权完成本地项目、GitHub 三条 AI 分支和 Cloudflare 的同步发布。
首次完整成功的应用提交为 `3200806ebc7ff12ef8ba27ecae9ea1958c5880b2`，
Worker 版本 `cff521a1-5ae5-4d52-a5b8-fa702d05b5c1`，已读取部署元数据确认 100% 流量。
本次收尾文档随后随同一代码再次同步；最终 SHA/Version ID 记录在本机 `outputs/ai-office-sync/` 发布回执，
也可用 `wrangler deployments list --json` 的发布注释核对，不把早期失败提交当作线上版本。

公开页面正常浏览器 HTTP 200、无页面脚本错误，七个关键静态资源 SHA256 与发布目录一致；
`/api/config` 为 200，四个新增办公接口未登录均为 401。
直接 urllib 请求被 Cloudflare 1010 拦截，已改用正常浏览器完成验收，没有关闭站点防护。
未使用真实所有者账号发送客户回复、执行退款/处罚或发布商品；这些真实客户业务不属于发布探针。

正式 Worker Pillow 已通过 12.3.0 Wasm 构建和运行验收，源码/制品来源已锁定；
本地原 `python_modules` 12.2.0 完整归档于 `_local/worker-python-modules-before-12.3-20261023/`，
原 Windows `.venv-trial` 依赖和十九个待提交源码文件保留。
当前绑定 D1 仅新增空的 `ai_office_jobs`，未导出真实全库，未合并其他数据库。

后端 562 项、前端 11 脚本、四个工单浏览器场景、上游办公查询/尺寸浏览器验收通过；
GitHub `3200806` Postman CI 成功。数字商品正式发布、模型自托管及通用长任务 Agent 仍待后续切片。


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
其他数据库的权威关系仍需运维确认；本轮已按授权对当前线上绑定库新增确认表并部署，不自动合并多库。

## 后续顺序

本轮已完成受控发布与公开页面/鉴权探针；下一轮再推进数字商品完整发布/交付切片，并单独验收真实客户业务。
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

### 授权后的上游整合

用户已明确授权本地 E 项目、GitHub 三条 AI 分支、当前绑定库仅新增空确认表及 Cloudflare 发布，禁止全库导出。
授权后复核发现 `feature/ai-support-rag` 已新增 `8500d30`；本轮保留该提交，避免回退已有面板尺寸修复。
与此前已验收版本相比，业务 Python 代码及单元测试正文不变；新增上游浏览器脚本，补齐第七个工单入口和视口恢复断言。
已实际运行 `office_mode_browser_smoke.py`：真实内存查询、列表渲染、手机号打码、七个快捷入口、底部不裁和缩小后恢复尺寸均通过。
执行环境为原项目 Python 3.12.7 的 Playwright，数据仅为脚本合成，未访问线上业务。

### 发布运行时兼容修复

授权后已对当前绑定库仅执行 `CREATE TABLE IF NOT EXISTS ai_office_jobs`，七列结构及零行均核验通过；未修改已有业务记录。
原工作区已快进至整合提交并恢复全部待提交内容；十九个文件有私密恢复快照，十七个不重叠文件保持内容，九十一个既有 Python 函数保留。

第一次真实发布被 Cloudflare 校验拒绝（10021）：`ModuleNotFoundError: No module named workers`，提示需要外置 SDK 或内置 SDK 兼容标志。
原线上兼容日期同为 2026-10-17，代码此前依赖平台内置 SDK；本轮保持该日期，显式添加 `disable_python_external_sdk`。
该标志只选择 SDK 来源，不降低 TLS、KDF 或 Pillow 版本，不自行拼装 SDK。
依据 Cloudflare 官方运行时定义：
https://github.com/cloudflare/workerd/blob/main/src/workerd/io/compatibility-date.capnp （pythonExternalSDK）。
首次失败没有产生成功部署回执；新增空确认表保留供重试，未执行全库恢复或删除业务表。

### 正式 Pillow Wasm 制品验收

SDK 修复后的第二次真实发布仍被 10021 拒绝，原因是缺少 PIL；原本地旧依赖实际为 12.2.0，未复制到线上。
官方 PyPI 12.3.0 元数据没有 Wasm wheel；Pyodide 官方 314-20260911 索引也仍为 12.2.0。
本机 WSL Ubuntu 报 `ERROR_NO_SYSTEM_RESOURCES`，没有更改系统配置或停止其他进程。

已复用官方配方，在隔离 GitHub Linux CI 构建正式 Pillow 12.3.0：
https://github.com/wangzirui471-collab/huali-corner/actions/runs/39906746810 （成功）。
真实 Wasm 验证 JPEG/PNG/WebP、EXIF、坏图拒绝和像素上限通过，非 Windows Pillow 冒充平台验收。
源码 SHA256、配方引用、制品来源及 wheel SHA256 已锁定在 `Backend mission/worker-pillow.lock.json`。
连接器下载 artifact 后核验摘要 `a1004c5ed59b55ed3464d17f3b705166127a179045ac9d672c7e578581535c15`。
安装器实际检查通过，并以 Python -O 负向确认旧版证明会被拒绝，然后只安装到独立发布目录。
GitHub Postman CI 的 `ffde073`、`b799054` 已成功；正式 Worker 重新发布结果另记发布回执。
