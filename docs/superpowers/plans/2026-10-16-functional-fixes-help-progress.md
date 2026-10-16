# SDD ledger — plan: docs/superpowers/plans/2026-10-16-functional-fixes-help.md

基线2350a87，当前功能分支内直接执行，业务不进入main。用户本轮明确要求修复全部8类确认问题，另选择校园互助“发布需求＋私聊协商”。

Pre-flight: Task 1/2共享工单/消息DTO与增量迁移；保持原字段，增加restricted、related_ticket_id和成员游标。Task 3沿用帖子/私聊/客服，不建立服务资金或抢单接口。

Task 1/2: RED记录为/tmp/zj-fixes-red.log（6个新Python场景全部失败）、frontend_functional.test.mjs依次揭示卖家按钮、角色载荷、缓存清理失败；GREEN为113项Python、前端功能回归与模块自检通过。

Task 1/2: 已实现工单摘要/详情分权、转派撤权、未交付退款归一化、结案只读与关联申诉、卖家角色表单/取消通知、私聊双向名称/持久游标/幂等通知、设备缓存清理。网页读取标记在可见会话且已加载消息后提交。

Task 3: RED为/tmp/zj-help-red.log，5个场景因publish_help缺少而失败；实现待进行。
