# 八类缺陷修复与校园互助实施计划

> 执行方式：在当前功能分支内直接执行，使用superpowers:executing-plans；先失败回归、再实现，完成后独立整体验证。

**Goal:** 修复2026-10-16检查报告的8类问题，并按用户已选“发布需求＋私聊协商”扩展现有社区。
**Architecture:** 保持分层、增量迁移和模拟交易。互助复用社区帖子、私聊、举报与客服，不创建服务支付/抢单系统。
**Tech Stack:** Python/SQLite、原生ES模块、既有小程序工具、unittest/Node/Chromium。
**Spec:** `/workspace/转角-功能缺陷检查-2026-10-16.md`及用户本轮回复；本计划同时记录已选互助范围。

## Global Constraints
- 业务进入Backend mission/app各领域；网页进入src各层；不覆盖main，不带真实数据。
- 保留DELETE事务、整数分、旧订单和所有历史数据；新列/表增量建立。
- 互助首版仅发布＋私聊：类别、需求/服务方向、标题、报酬意向、公共地点、截止时间、说明；作者关闭/重新开放；不真实收费、不声称平台担保。
- 快递代取、资料代交、搬运、学习辅导/笔记和其他合法互助先开放；“代课”含义待用户补充，沿原需求不提供代考/代签到类别。

## Review Focus
- 转派后的旧客服和未认领客服不能从订单/工单/图片绕读私密材料。
- 已结案重复审批仍幂等，但新材料须走关联申诉，不能假成功或重复退款。
- 消息读游标只覆盖本次已展示消息，不吞掉刚到的新消息；重试不重复通知。
- 退出清理只作用当前账号本机缓存，保留服务器草稿和其他账号数据。
- 互助关闭/过期不能继续招募，非作者不能改状态，公开字段不作为真实收款或学籍认证。

## Task 1: 权限、卖家订单和售后闭环
**Files:** app/support/access.py、support/service.py、support/evidence.py、trade/service.py、core/database.py；网页pages/orders.js、pages/support.js、actions/trade.js、actions/support.js。
**Interfaces:** 工单DTO增加restricted与related_ticket_id；未分配客服只取摘要；关联申诉保留原工单。卖家待付款只提交appointment；取消通知发另一方。未交付误选退货时归一化为无需退回，历史错选也能合法退款但不生成虚假退货链。
- [x] 写tests/test_functional_fixes.py及tests/frontend_functional.test.mjs对应失败用例并运行。
- [x] 实现权限收口、角色表单、取消通知、退款纠错、结案只读及关联申诉。
- [x] 定向测试通过，提交。

## Task 2: 私聊未读、对方名称与退出清理
**Files:** app/community/migrations.py、community/service.py；src/core/inbox.js、core/account-cache.js、auth/login.js、actions/account.js、pages/messages.js、actions/inbox.js；server.py。
**Interfaces:** members增加last_read_message_id；POST /api/messages/read带room_id和through_id；rooms返回peer_id/name/unread_count/last_message；私聊通知entity_type=chat，通知已读与会话已读各有明确起点。
- [x] 写消息重试、双向名称、游标范围、转号缓存失败用例并运行。
- [x] 实现双向视图、持久游标/私聊通知、网页读标记与路由、当前账号退出清理。
- [x] 定向测试通过，提交。

## Task 3: 社区校园互助首版
**Files:** app/community/help.py、community/migrations.py、app/market.py、server.py；src/components/help.js、pages/help.js、actions/help.js、pages/community.js、router.js、actions/index.js；小程序既有hub入口。
**Interfaces:** GET/POST /api/help/posts，POST /api/help/status；表service_posts关联posts；金额reward整数分，输入reward_yuan严格解析；举报/反馈使用post_id关联工单。无真实服务订单/支付。
- [x] 写tests/test_community_help.py与浏览器互助发布/联系/关闭/反馈流程，确认新能力缺失时失败。
- [x] 实现点选发布、筛选、联系作者、关闭/重新开放及关联工单；静态演示只读守卫。
- [x] 回归并提交。

## Task 4: 完整验证和交付
- [x] 跑全部Python/Node及代表性Chromium流程，检查旧数据迁移、静态演示与干净源码包。
- [x] 独立审查本轮差异，重要问题补先失败回归后修复。
- [x] 更新需求状态/说明，打包，推送功能分支，报告未测设备和剩余后续功能。
