# 分层整合执行记录

用户已明确同意既有方案并要求按分层开始，继续当前会话执行，不重新审批同一范围。云环境已隔离，使用现有仓库独立功能分支，不额外建 worktree。

- 基线：origin/main ad39da0，Python55、ES31、原生3通过。
- Task 1 RED：8个草稿测试均因缺少save_draft等接口失败。
- Task 1 整合：仅迁移旧分支相对共同基点的函数变更，保留用户主线非重叠方法；publish合并电子分类，order_action保留卖家付款前取消。
- Ruling: 两个旧信誉测试改用已批准的规则处罚接口，保留无关人员/重复处罚/低分不能发布断言；旧自由调分返回410，避免重新开放规则绕过。代价：旧调分调用方需使用规则接口。

Task 1 complete: Python 92/92，含电子产品草稿、付款前移除商品和留言、通知、重启及DELETE日志共存。未迁入WAL设置。

Task 2 complete: 网页按core/components/pages/actions迁移；49个ES模块真实加载且新增显式依赖图无环检查。小程序保留主线样式、电子分类、卖家下架和付款前改单；新增features分包。8个原生Node脚本与独立网页会话竞态脚本通过。
Task 3 complete: 编辑5个原始用例RED→GREEN；补充欺诈卖家取消订单后库存不可复活用例RED→GREEN。商品版本、移除原因、报价版本和完整订单快照已增量接入。
Task 4 complete: 组合筛选5个用例RED→GREEN；500件数据匹配、游标条件绑定、同价去重、送货总价及未知版次通过。
- Ruling: 商品编辑未提交修改仅本机缓存；发布草稿仍服务端保存，避免自动保存即修改公开商品。代价：编辑缓存不跨设备，文档与表单已说明。
- Ruling: 历史移除原因不猜为主动下架，保留legacy_unknown等待人工核对。代价：少数历史商品不能一键恢复，换取不绕过退款和实物链。
- 补充故障：发布请求晚返回时会清掉同账号新草稿、跳走新页面；frontend_session.test.mjs先观察失败，再加编辑器标识和可见代次检查验证通过。
- 布局回归：空筛选摘要使首张商品y=620.8；去掉空摘要后保留原首屏<600检查通过。旧浏览器脚本选择器改为表单内textarea，未删除实际交互。
- 构建测试先因缺少打包器失败，增加白名单源码ZIP后通过；启动脚本取消按端口强杀进程，保留手动选择8081和错误信息。

Task 5 pre-review: Python105/105、ES49、native8、frontend_session通过；layered_browser8组、public_demo_smoke、ui_redesign_smoke、browser_smoke和源码包解压启动验证全部通过。源码包不带运行数据，Windows/微信原机未执行。

Final review: fresh independent reviewer completed; 3 Important/P2, no Critical or confirmed Minor. Initial requested model was unavailable due usage quota; next available independent model completed the read-only review.
Final: fixed buyer restriction/checkout race — test_fraud_restriction_committed_before_checkout_write_is_respected RED→GREEN.
Final: fixed private proof loss on price-only edit — test_price_edit_preserves_server_owned_private_purchase_proof RED→GREEN; public DTO still hides proof.
Final: fixed old upload overwriting newer suspended draft recovery — frontend_cache.test.mjs actual delayed upload RED→GREEN; durable editor generation remains after suspension.
Final verification: Python107/107; ES49 with graph; frontend_session + frontend_cache; native8; layered_browser8 journeys + legacy browser + static subpath + redesign4 widths; clean source ZIP startup all pass. No deferred minors or declined finding rulings; Windows/WeChat/public/real payment remain unverified scope.
