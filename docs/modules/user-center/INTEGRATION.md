# 用户中心 U01 接入合同

日期：2026-10-17（Asia/Shanghai）。B 侧第一阶段交付，目标分支 `feat/layered-completion`。

起始提交：`b59096c471acf162c0072f6ec324a7675c1415a2`。

## 交付状态和边界

U01 提供资料领域方法、增量迁移及测试源码，供 A 接线；后续 U02 的专用媒体合同见 AVATAR_INTEGRATION.md。
未编辑公共入口，尚未注册新的 HTTP 路由，也未替换旧 AccountService 方法。
本文件中的接线片段是给 A 的修改建议，不是本分支已经执行的改动。

用户随后明确要求：不再在本机创建数据库，不再运行测试，正确性只做只读检查，测试交给 A/用户。
此前已执行过的测试结果仅作为历史记录；新增调整不据此声称通过。

## 1 迁移入口

导入：

```python
from ..account.migrations import migrate_account
```

A 在 `app/core/database.py` 的 Store 初始化现有 `with self.connect() as c:` 中，
在 users 基础表及 is_active 等原有列创建后调用：

```python
migrate_account(c)
```

函数签名：`migrate_account(connection: sqlite3.Connection) -> None`。
它不提交事务、不改变连接配置，只新增缺失列，并且只向本次新建的选项列映射历史 education。
已经存在的新列不覆盖，原 education 不变；支持完整重跑和部分列已经存在的旧库。

| 列 | 定义和默认值 |
| --- | --- |
| degree_level | TEXT 非空，bachelor/junior_college/other/unspecified，默认 unspecified |
| study_status | TEXT 非空，studying/graduated/other/unspecified，默认 unspecified |
| profile_version | INTEGER 非空、非负整数，默认 0 |
| avatar_upload_id | 可空 TEXT，U02 保留位 |

历史“本科/专科”仅映射学历；“已毕业”仅映射毕业状态；其他、空值与未知值映射 unspecified。
新增账号默认两项未知，不能把注册时旧 education 默认“本科”视为本人已选学历。
若原本已有列，迁移不擅自改约束或修复其异常值，A 升级副本时应另行确认历史结构。

## 2 Market 装配

A 在 `app/market.py` 导入并加入现有组合类：

```python
from .account.profiles import UserProfiles
```

`UserProfiles` 没有自定义构造函数，不会覆盖 Store 初始化；它依赖现有 `connect()`、`tx()`、`trial`。
没有与原 `profile`、`update_profile`、`user` 或密码方法同名的方法，不依赖多继承顺序替换认证。

## 3 原 AccountService 的兼容转发

A 仅替换 `app/account/service.py` 中原资料方法的方法体，其他认证逻辑保持：

```python
def profile(self, u):
    return self.user_profile(u)

def update_profile(self, u, d):
    return self.user_update_legacy_profile(u, d)
```

新领域读取直接查询 users，不调用旧 profile，因此没有递归。
原 `/api/me` 的响应继续是用户对象，原公开 `/api/profile?id=...` 继续是 `{user, products}`。
原 id/nickname/college/major/education/bio/role/score 的字段名和类型不改，新增字段为加法扩展。

旧写入兼容规则：

- nickname 沿用非空、去除首尾空格、最长24字规则。
- major/bio 和非试用 college 沿用原转换/截断策略；新接口的超长值则明确拒绝。
- 试用 college 始终由服务端固定为计算机工程学院。
- education 缺失或与当前已返回值相同时，保留 degree_level/study_status；明确改变时按任务书映射。
- 未知历史 education 未被明确改变时保留原值，不通过读操作改写资料。
- 旧请求中的 role/score/user_id 等未知字段不会写入数据库。
- 每次成功资料保存递增 profile_version；旧客户端可不带版本，带版本则严格校验。
- **兼容限制：**不带版本的旧客户端不能阻止另一旧页面的覆盖；其保存仍会使新客户端持有的旧版本失效。

必须同时接通这两条旧方法的转发，不能只新增路由却让旧客户端继续绕过版本更新。

## 4 新资料 HTTP 路由

将以下分发放在 `u = self.uid()` 之后，actor_id 只来自该有效会话：

```python
if p == '/api/user/profile' and method == 'GET':
    return self.respond(m.user_profile(u))
if p == '/api/user/profile' and method == 'POST':
    return self.respond(m.user_update_profile(u, data))
```

| 方法 | 输入 | 输出 |
| --- | --- | --- |
| user_profile(actor_id) | 会话用户的整数 ID | UserProfileDTO |
| user_update_profile(actor_id, payload) | 版本必填，其余编辑字段可部分提交 | 更新后 UserProfileDTO |
| user_update_legacy_profile(actor_id, payload) | 原 /api/me 参数；可选版本 | 更新后 UserProfileDTO |

新 POST 白名单仅为 nickname、major、bio、degree_level、study_status、profile_version。
不允许 education、college、头像、手机号、身份、权限等其他字段；出现即400，不悄悄忽略。
枚举严格使用机器值；版本必须是非负整数，拒绝 JSON 布尔、小数、字符串、null 和缺失。

写入在既有 `tx()` 内读取当前资料、检查 is_active、核对版本并递增；无效会话由 HTTP 层拒绝，
领域方法额外拒绝无效 actor_id、未知账号和停用账号。角色/信誉/订单/认证字段均不参与资料 UPDATE。

`user_profile` 是内部按 ID 读资料的方法，为兼容历史调用不在读路径拒绝停用账号。
HTTP 自查入口仍必须 `self.uid()`，不能把 URL/body 中的用户 ID 传作自查 actor_id。
公开主页按目标 ID 读取时继续使用公开 DTO 允许字段，不暴露 is_active、手机号或地址。

## 5 请求与响应例子

```json
{
  "profile_version": 0,
  "nickname": "示例同学",
  "major": "软件工程",
  "bio": "继续分享闲置",
  "degree_level": "junior_college",
  "study_status": "graduated"
}
```

成功响应示意（ID/版本随真实数据变化）：

```json
{
  "id": 101,
  "nickname": "示例同学",
  "college": "计算机工程学院",
  "major": "软件工程",
  "education": "已毕业",
  "bio": "继续分享闲置",
  "role": "user",
  "score": 100,
  "degree_level": "junior_college",
  "study_status": "graduated",
  "profile_version": 1,
  "avatar_upload_id": null,
  "avatar_url": null
}
```

错误沿用 DomainError 与现有 `{error: "可读说明"}`：

| HTTP 状态 | 条件 |
| --- | --- |
| 400 | 无效字段、文本超长、枚举或版本不合法 |
| 401 | 无有效登录，或领域 actor_id 不合法 |
| 403 | 写入时账号已停用 |
| 404 | 用户不存在 |
| 409 | 资料已更新，请重新载入并核对 |

新方法返回数据，不返回 HTML；页面展示 nickname/major/bio 时仍必须转义。

## 6 U02 U03 的保留合同和接线需求

- U02 已编写专用头像领域，资料 DTO 返回当前有效的公开头像路径；无效或无头像时为 null。
- U02 的 `user_upload_avatar`、`user_set_avatar`、`user_is_public_avatar`、`user_avatar_bytes` 接入见 AVATAR_INTEGRATION.md，尚未由 A 接线验证。
- U03 继续交付独立 `actions/user-profile.js` 的 clicks/submits、`user-` 动作及表单 ID。
- 此阶段没有前端动作/表单/样式需要 A 注册；不要提前引用不存在的文件。
- 现有 core/http.js 抛出的 Error 未携带 HTTP status。U03 需要明确区分409；建议 A 后续在原错误上增加只读的 status 属性，保留 error/message 与既有调用方式。B 不另建请求/共享状态实现。
- 两阶段接线后分别合入 A 的提交，才能验证真实 HTTP、旧小程序兼容和页面保存。

## 7 给 A 的验证清单

按用户最新要求，本机不再执行下列数据库/页面测试，由 A/用户在自己的隔离环境运行：

```powershell
$env:PYTHONPATH = "$PWD\Backend mission"
python -m unittest discover -s tests -p test_user_profiles.py -v
python -m unittest discover -s tests -v
node tests/frontend_modules.test.mjs
```

接线后需要真实 HTTP 覆盖：新账号/历史账号 GET，自查未登录401，版本0保存成功、重复旧版本409，
禁止字段400且数据库不变，旧客户端同值/缺失 education 保留新字段，停用后会话失效，
公开响应无手机号/地址且形状仍为 `{user, products}`，旧网页和小程序仍能登录与保存。

原基线在当前 Windows 环境有 SQLite 临时文件占用清理错误与中文路径前端自检错误，见 DELIVERY.md。
不能把领域用例的历史通过结果当作全套回归通过。

## 8 A 接入后回填

| 接入项 | A 提交与位置 | 当前状态 |
| --- | --- | --- |
| Store 调用 migrate_account | 待 A 填写 | 未接入 |
| Market 组合 UserProfiles | 待 A 填写 | 未接入 |
| AccountService.profile/update_profile 转发 | 待 A 填写 | 未接入 |
| /api/user/profile GET/POST | 待 A 填写 | 未接入 |
| 公开 DTO 与旧客户端兼容 | 待 A 验证 | 未联调 |
| U02 媒体钩子 | 见 AVATAR_INTEGRATION.md | 已写领域代码，待 A 接入 |
| U03 动作和样式 | 后续阶段 | 未实现 |
