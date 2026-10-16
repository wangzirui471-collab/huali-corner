# SDD ledger — plan: docs/superpowers/plans/2026-10-16-functional-fixes-help.md

基线2350a87，当前功能分支内直接执行，业务不进入main。用户本轮明确要求修复全部8类确认问题，另选择校园互助“发布需求＋私聊协商”。

Pre-flight: Task 1/2共享工单/消息DTO与增量迁移；保持原字段，增加restricted、related_ticket_id和成员游标。Task 3沿用帖子/私聊/客服，不建立服务资金或抢单接口。

Task 1/2: RED记录为/tmp/zj-fixes-red.log（6个新Python场景全部失败）、frontend_functional.test.mjs依次揭示卖家按钮、角色载荷、缓存清理失败；GREEN为113项Python、前端功能回归与模块自检通过。

Task 1/2: 已实现工单摘要/详情分权、转派撤权、未交付退款归一化、结案只读与关联申诉、卖家角色表单/取消通知、私聊双向名称/持久游标/幂等通知、设备缓存清理。网页读取标记在可见会话且已加载消息后提交。

Task 3: 初始RED为/tmp/zj-help-red.log，5个场景因publish_help缺少而失败；后续已实现并转绿。

Task 3: complete — 网页/小程序校园互助发布、公共筛选、联系私聊、作者关闭、关联客服已实现；无服务订单/真实支付。

Final review: 独立review_functional_help确认3项P2；退出竞态、原生切群游标、普通列表遗留关闭互助均已先失败后修复。没有搁置的重要发现。

Final: fixed 3 P2 — frontend_logout_race.test.mjs、native_client.test.js、test_structured_help_never_leaks_as_unlabelled_generic_recruitment均RED→GREEN，完整Python123/123，网页54模块、原生10脚本及Chromium流程通过。

Task 4: complete — 完整回归、独立审查修复、需求V1.4/原生Word、实际交付ZIP校验与空库启动、GitHub功能分支推送完成。远端46be164已确认；本次最终文档记录提交随后一并推送。不把本机源码、静态演示或Node逻辑测试称为公网/微信实机通过。
