# 本轮验证记录（2026-10-23，AI 工单切片）

## 环境与数据

- 独立克隆基线 `b70d0de8acb1a1e6a081ec9b2188024d5ff6c598`，不是原电脑工作区。
- Windows，Python 3.12.14，Pillow 12.3.0，隔离补齐 PyMySQL 1.2.3；Node 24.21.0。
- LangGraph 1.2.16 及其实际安装的 38 项依赖锁定在 `ai_service/requirements-office.lock`。
- 全部工单、账号、会话与消息均为合成数据；D1 采用内存 SQLite 适配，浏览器夹具只监听回环地址。
- 没有执行生产 API、真实数据库迁移、部署、收费模型调用、TLS 绕过或密码 KDF 降级。

## 已实际通过

| 检查 | 命令/方式 | 实际结果 |
| --- | --- | --- |
| 接手基线 AI | `python -m unittest discover -s tests -p test_ai_support.py` | 49 项通过 |
| 接手基线前端 | `node tests/frontend_modules.test.mjs` | 55 模块可加载 |
| 新工单回归 | `python -X utf8 -m unittest discover -s tests -p test_office_tickets.py` | 18 项通过 |
| 真实 LangGraph 图 | 安装可选依赖后运行 `test_office_agent.py` | 5 项通过，未调用付费模型 |
| 收尾全量后端 | 安装正确依赖后 `python -X utf8 -m unittest discover -s tests` | **545 项通过**，211.042 秒 |
| 前端检查脚本 | 逐个执行 `tests/*.test.js`、`tests/*.test.mjs` | **11 个文件全部通过**；当前 56 模块可加载 |
| 前端生产构建 | `cd office-ui; npm run build` | 成功；JS 367.67 kB、CSS 361.89 kB，均仅办公入口按需加载 |
| 真实 UI → 业务 API | `office_browser_fixture.py` + `office_tickets.browser.mjs`，实际构建包 | 桌面、手机和过期快照三个场景通过 |
| 独立服务 HTTP | 本地启动 `ai_service/server.py` 并请求办公草稿 | 有效令牌返回 `engine=langgraph` 的规则草稿；错误令牌 401 |
| 补丁格式 | `git diff --check` | 通过 |

浏览器场景覆盖：从小转按钮读真实明细、内部备注不外泄、编辑公开正文、取消后零写入、
确认后受理/回复/通知、相同预览重复提交不重复回复、新消息阻止旧列表生成草稿、
390px 手机无横向溢出、退出登录清除面板。夹具运行的是实际 Python 业务路由和内存 D1，
没有用固定 JSON mock 代替整个后端。

## 已记录失败及修复

1. 新工单测试首次 **13 项失败**：聊天没有明细，新增工具返回 501；实现后通过。
2. LangGraph 测试首次 **5 项失败**：尚无编排接入；接入真实 StateGraph 后通过。
3. 首次全量 **535 项，3 失败 + 1 错误**，均在 `test_trial_launcher`：
   `test_check_mode_does_not_create_trial_data`、`test_probe_reports_actual_interpreter_and_dependencies`、
   `test_server_preserves_original_working_directory_and_database_environment`、
   `test_missing_pillow_interpreter_does_not_hide_working_interpreter`。原因是当前解释器缺 PyMySQL 1.2.3；
   在仓库外补齐隔离依赖后，启动器 6 项及中间全量 541 项、最终 545 项通过，未放宽版本检查。
4. 一次 Cloudflare 子集因 SQL 新增中文注释与旧测试的默认 GBK 读取冲突报 8 个错误；
   保持 schema 为 ASCII，并以 UTF-8 运行收尾全量，未把问题当平台故障。
5. 独立审查发现批量守卫从四条起超 D1 单条查询 100 参数，以及草稿静默接受未展示的新消息；
   两项先补失败测试再修复。二十条合成 Paid 批次现在逐语句检查参数上限，且仍只有一个事务 batch。
6. 补充 Free 每调用 50 查询预算测试：缺省逐单，包含关联订单/商品的列表、草稿、准备、确认均在模拟预算内。
7. 首次手机测试被缺少的 Element Plus 遮罩样式挡住点击；使用官方完整样式后实际手机测试通过。
8. 首次构建许可脚本路径错误；修复路径后 `npm run build` 与开源许可产出通过。

## GitHub CI 与未验证能力

已读取 GitHub：`b70d0de...` 的 combined status 为空。AI 分支最近一次列出的 Postman CI
[成功运行](https://github.com/wangzirui471-collab/huali-corner/actions/runs/39893025030)
对应 **`7f4998c6...`**，不能作为基线 b70 或本补丁已通过 CI 的证据。
本补丁创建 PR 后的 CI 应另行检查。

尚未验证：真实 Worker/Pyodide、真实 D1/R2、生产账套与账号、实际外部模型、自托管推理、
公网 HTTPS 草稿服务、原电脑未提交修改及真实手机微信小程序。
本轮没有部署新版本，用户提供的线上 `d45cc213` 未在本轮重新发布或确认。
旧本地业务 server 的办公 API 尚未接入，不能宣称三端同步完成。

## 三方同步前的增量验证（2026-10-23）

- 上游已从 b70 更新至 `7fd4e15`；本轮整合后全量 **562 项通过，213.202 秒**。
- 将原目录已有查询测试带入独立克隆后复现概览 `KeyError: today`（65 项中 1 错误）；保留原目录修复后通过。
- 新增整合回归先失败：已解决工单被待办工具截走；保留原只读查询分流后通过，工单专项现为 19 项。
- 审查复现上游 global 请求换号后接受旧账号数据；先新增失败测试，再修复会话守卫。
- HTTP/cache 9 项与 session 9 项通过，独立复核再跑通过；11 个前端脚本通过，模块仍为 56 个。
- Vue 生产包重建成功：JS 367.71 kB，CSS 361.89 kB；实际包浏览器四个场景通过。
  新场景覆盖退出清空已显示内容、拒绝延迟旧回答、隐藏 owner 控件、下一账号 history 为空。
- Worker 4.151.1 dry-run 通过：61 个附加模块、143 个静态文件。没有使用 remote:true 做本地运行验证。
- 已只读核对线上版本、当前绑定库标识与 Time Travel 恢复书签；完整 D1 导出因敏感数据审批被拒绝，未执行。
- 本节是发布前证据，不能据此声称真实 L1 线上写入、数据库迁移或三方发布已经完成；实际状态另记发布回执。

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

## 实际发布后的验收

- 正式 Pillow 12.3.0 装入独立发布目录后，真实 Cloudflare 发布成功：提交 `3200806`，
  Version `cff521a1-5ae5-4d52-a5b8-fa702d05b5c1`，启动 992ms，上传压缩后 1482.41KiB。
- 平台元数据再次读取确认该版本 100% 流量，兼容日期仍为 2026-10-17，保留原有绑定、变量与密钥。
- 公开 urllib 检查先得到 Cloudflare 403/1010；正常未登录 Chromium 浏览器验收成功，未修改 WAF/TLS。
- 浏览器根页面 HTTP200、页面脚本错误 0；七个关键 JS/CSS 逐字节 SHA256 匹配。
- `/api/config` HTTP200 且为 JSON；四个新增办公接口匿名 POST 均为401，未发送客户消息。
- GitHub Postman CI `3200806` 成功：
  https://github.com/wangzirui471-collab/huali-corner/actions/runs/39907687964 。
- 原本地项目 HEAD 和发布源码一致，未提交 Postman、导购、推荐等内容保留；
  旧 Wasm 依赖整体归档后安装相同正式 12.3.0，Windows 依赖未改动。
- 本收尾文档再次同步后的最终版本见本机发布回执；实际客户工单写入、真实小程序和外部模型调用仍未验收。
