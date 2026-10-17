# 用户中心实施计划

> 执行方式：本聊天使用 executing-plans 与 test-driven-development 自行实施；按既定 A/B 接线阶段交付。

**Goal:** 完成 B 侧 U01、U02、U03，保留原账号、交易数据与客户端合同。

**Architecture:** 沿用 Python Market 领域组合、SQLite 既有事务及原生 ES 模块。B 新增资料/头像领域类、迁移、用户页面与专属测试，A 独占公共装配与入口。

**Tech Stack:** Python 3.12、SQLite DELETE 日志模式、Pillow、原生 JavaScript ES 模块。

**Spec:** `docs/用户中心开发任务书-v1.0.md`、`docs/双人开发分工与验收任务书-v1.0.md`、`docs/转角软件开发规范-v1.0.md`；用户 2026-10-17 确认按 B 范围开发、由 A 统一接线。

## Global Constraints

- 起始提交：`b59096c471acf162c0072f6ec324a7675c1415a2`；分支 `feat/user-center`，独立克隆，不修改原 main。
- 不改 `server.py`、`app/market.py`、`core/*`、`account/service.py` 及公共前端入口。
- 新方法带 `user_` 前缀；不覆盖 `profile` / `update_profile`，不调用它们造成递归。
- 迁移增量且重复执行不覆盖用户选择；仅使用独立临时数据，不操作实际 var/var-trial。
- 保留旧字段和错误形状；新写入白名单、严格字段类型和版本比较在既有写事务内完成。
- 模块通过不等于 HTTP、网页或全软件验收通过；需等 A 接线后联调。
- 用户在实施中明确：不再在本机创建数据库/运行测试，B 后续仅做只读检查，运行验收交 A/用户。下列测试步骤保留为交付验证合同，不能自行继续执行。

## Review Focus

- 部分迁移的旧库：只映射本次新增的列，不能覆盖已有新字段。
- 已毕业与未知旧值：不推断学历，不改原 education，旧客户端同值保存不丢新选择。
- 布尔/浮点版本与非法字段：拒绝且事务无副作用。
- 真正并发保存：不同连接读取相同版本，只一笔提交成功。
- 停用账号与跨账号：认证主体由 A 的会话解析，领域写入复核 is_active，禁止 body 指定身份。

## Task 1: U01 资料与迁移

Files: 新增 `Backend mission/app/account/migrations.py`、`profiles.py`、`tests/test_user_profiles.py`。

Interfaces:
- Consumes: `self.connect()`、`self.tx()`、`self.require()`、`self.trial` 与现有 users 表。
- Produces: `migrate_account(connection)`、`UserProfiles.user_profile(actor_id)`、`user_update_profile(actor_id, payload)`、`user_update_legacy_profile(actor_id, payload)`。

- [x] 编写迁移、字段白名单、DTO、边界、版本竞争和旧客户端行为测试。
- [x] 执行专属测试，确认缺少新模块导致失败（停止测试要求之前）。
- [x] 实现列级增量迁移；新增枚举值、非负整数版本与头像引用保留位。
- [x] 实现显式 DTO；新资料仅允许 nickname/major/bio/degree_level/study_status/profile_version。
- [x] 实现旧资料适配；education 缺失或同值时保留新选项，所有成功保存递增版本。
- [x] 只读审查、记录原基线问题；历史33项通过，但最终测试夹具调整未运行。
- [x] 完成 INTEGRATION.md 与 DELIVERY.md，准备供 A 接入评审的阶段提交。
- [ ] A/用户运行最终夹具与真实接线回归；通过后才能标记 U01 已完成。

Run: `python -m unittest discover -s tests -p test_user_profiles.py -v`。
Expected: 专属用例全部通过，迁移/校验失败不改变原数据。

## Task 2: U02 头像领域实现

Files: 新增 `account/avatars.py`、`tests/test_user_avatars.py`，扩展本领域迁移和文档。
Interfaces: 复用 U01 profile_version；新增 user_upload_avatar/user_set_avatar/user_is_public_avatar。

- 用户于本轮要求先继续完成 U02/U03 的 B 侧实现；不再等待 A 接线才写代码，公共文件仍归 A。
- 头像使用独立 user_avatar_uploads 表（仍存运行 uploads/），不改变旧 uploads 表列数，避免破坏原位置式 INSERT 或被当成商品/证据图。
- [x] 编写坏图、体积/像素、多帧、元数据、所有权、公开资格和失败补偿测试源码，不运行。
- [x] 实现专用上传、选择、移除与公开头像投影；只读检查。
- [x] 提交媒体/备份接入清单与独立 U02 提交。
- [ ] A 接线后执行真实 HTTP 与旧客户端兼容验证（由 A/用户运行）。

## Task 3: U03 网页实现

Files: `pages/me.js`、新增 components/user-profile.js、user-avatar.js、actions/user-profile.js、user-center.css、tests/user_profile.test.mjs、user_center_browser_smoke.py。

- [x] 编写表单、跨会话晚响应、409 保留输入和文本转义测试源码，不运行。
- [x] 实现表单/头像/公开主页，保留原入口，动作键以 user- 开头。
- [ ] A 注册动作和样式后运行真实页面联调、四档宽度与截图。
- [x] 记录未运行项及只读审查结果，三个任务分别准备提交。
- [ ] A/用户运行相关回归并完成最终联合验收。

## 当前阶段

按用户最新要求继续交付 Task 2/3 的 B 侧代码；A 的接线和运行验证仍是联合完成条件，不能把未接线的功能声明为可运行验收通过。
