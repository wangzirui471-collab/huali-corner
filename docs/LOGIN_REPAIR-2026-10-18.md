# 线上登录与页面加载修复

日期：2026-10-18。网址：https://zhuanjiao.wangzirui471.workers.dev/

本轮已部署的 Worker 版本：8b56989f-b559-44cd-9747-d89d0f19f1b0。
部署前版本：caea020a-f5dc-452c-85c2-c61f4f5f800d。

## 问题与修复

1. 用户提供的地址是 /#staff。原 Worker 只移植了认证及商品等少量路由，客服页请求 /api/tickets、/api/admin 等得到 501，“我的”页的商品、订单、通知请求也缺失。补入独立 read_pages.py 异步读取适配，不修改原数据库结构或覆盖业务数据。
2. 浏览器真实复现 randomSaltHex 调用 subtleCrypto().getRandomValues 报 TypeError。已改为 window.crypto.getRandomValues，不使用 Math.random，不降低现有密码派生轮数。
3. HTTP 层直接 res.json() 导致 HTML 错误页暴露 Unexpected token '<'。现在检查响应类型，保留 HTTP 状态并给出可读提示；不会把失败响应当成登录成功。截图中那次具体 HTML 来源未被重现，不能断言一定是某一种 Cloudflare 错误。
4. 启动恢复会话只在明确 401 时清除 token，网络、503 和 HTML 响应保留会话。
5. 普通用户从 #staff/#admin 登录后返回商品首页，后台仍严格拒绝其读取管理接口；管理员和客服按原角色进入对应入口。
6. 公开卖家主页补齐商品卡要求的 nickname、卖家信息与互动字段；本人资料 GET /api/user/profile 使用本人活跃会话，不开放读取他人私有资料。

新增读取路由：health、my-products、orders、offers、notifications、badges、profile、user/profile、tickets、admin、audit、product/removed、admin/content、reconcile。notifications POST 仅标记当前用户自己的通知已读；其他库存、订单、退款和角色写操作未在本轮移植。

## 验证证据

- 新增 Node 传输/随机盐回归 5 项：先复现 3 个失败，再全部通过。
- Cloudflare 隔离 SQLite 回归最终 8 项通过，含未登录/普通账号/管理账号隔离、通知归属、个人订单、公开主页字段及本人资料版本。
- 完整 Python 回归运行过 305 项：298 通过、7 个历史 Windows 错误。审查后新增一项本人资料用例并加强主页字段断言，再跑最新 8 项通过；未把该阶段结果伪称为全量 306 项通过。
- 历史 7 项错误与 docs/ORGANIZATION_CHECK-2026-10-18.md 中同名项一致：test_http 的符号链接权限 1 项；test_operator_demotion 的临时 SQLite 文件清理 5 项、子进程编码 1 项。
- 前端 45 个模块可导入；用户中心与小程序客户端/订单/认证脚本通过。
- 真实 Edge 浏览器，1440px 桌面和 390px 手机视口：隔离账号登录客服概览、工单列表、个人页、订单、商品首页、卖家公开主页和本人资料页面通过，无 pageerror。
- 手机视口额外验证：注册、展示恢复码、退出重登、模拟 HTML503 后保留会话并刷新恢复；普通用户从客服链接登录回首页，客服接口仍 403。
- Workers 本机测试使用独立 D1/R2 本地绑定、合成账号和独立 state，不连接真实账号库进行写入测试。
- 发布 dry-run 及实际 deploy 成功；线上登录表单和安全随机盐生成在桌面/手机视口复查通过。
- 线上 health/products/public profile 返回 200 JSON；admin/tickets/my-products/orders/notifications/user-profile 在无会话时返回 401 JSON，已不是 501。
- 未在生产创建测试账号、改密码、注册或模拟下单；没有通过读取真实密码摘要或会话凭据绕过认证。因此生产真实账号的完整登录仍需用户设备复核。

## 数据与并行改动

没有执行 D1 schema 迁移、清库、重新导入、修改 R2 资源或付费计划，没有更改真实账号角色。已有未提交 UI 修改保留。只对原 index.html 的 main.js 入口增加本轮版本查询串，没有重写页面布局。

修改前的文件备份在 _local/site-fix-20261018-171441/，登录导航原件另存 _local/login-navigation-before-fix.js。未做强推、reset、合并或 Git 提交。本次线上修复应在后续版本管理时纳入，不能用旧分支覆盖。

## 仍需明确的范围

此站仍是部分业务完成迁移的云端试用版，不是全部本地功能都已上线。本轮恢复了认证脚本与上述页面的读取能力；发布、聊天发送、交易变更、退款处理、部分工单详情和管理端功能等未移植操作仍会返回明确未开放错误，不能称全站业务完成。管理员工作台 #admin 与客服工作台 #staff 不是同一套接口，本轮主要修复用户给出的 #staff。

普通注册账号不自动获得客服权限。建议重新打开 /?v=20261018-login-repair#home；工作人员可再进入 #staff。电脑可强制刷新，手机可关闭旧页后打开新链接；无需清除账号数据或重装环境。
