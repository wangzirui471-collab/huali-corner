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
