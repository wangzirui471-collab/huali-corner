# 转角分层整合与商品管理第一批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 以用户ad39da0分层结构为基础保留两条分支能力，交付商品编辑、可靠下架/恢复和组合筛选，不恢复旧平铺架构。

**Architecture:** 用户main为目录与界面基线，6286861为前两批功能迁移参考；新建集成功能分支进行定向迁移，不用旧目录覆盖新目录。Python领域服务由app/market.py装配，网页共享状态仅在core/state.js，动作与渲染分离，沿nav注册钩子避免循环依赖。

**Tech Stack:** 沿用Python/SQLite/Pillow、原生网页ES模块及微信小程序；保留DELETE日志和现有写事务组织，不引入框架迁移或付费服务。

**Spec:** docs/proposals/2026-10-16-转角未完成需求补齐方案.md，第2节状态校正、第3.1/3.2节及第4节第一批；用户2026-10-16对模块分层的最新约束见AGENTS.md。

## Global Constraints

- 用户已同意整体补齐方案；本计划落实第1批，后续客服三级退款、自动恢复、社区与正式上线沿后续批次推进，不把它们写成第1批已完成。
- 目录结构以ad39da0为准；保留电子产品、现有视觉/Logo资产、主动下架、付款前改订单/留言、静态演示ES模块导出。
- 将6286861中的草稿、客服、重售、信誉、通知与公共地点迁入分层服务；不得从旧分支恢复根目录market.py、web/app.js等业务入口。
- 不修改或清空原var/var-trial；旧订单快照与原账务不可被商品编辑重写。
- 书籍逐本定价，金额整数分，图片本人上传且至少正面/侧面/顶部三张；保留免费转让和电子产品类别。
- 信誉低于60不能发布/恢复；仅退款不恢复库存，退货重售须有实物与退款记录，不能用主动下架入口绕过。
- 全部资金仍模拟；不购买服务、不部署到外部、不擅自启用真实支付或迁移FastAPI。

## Review Focus

- 商品编辑、下架与下单发生并发时，使用事务内最新状态，订单快照和已锁定价格不变。
- 已退款或违规移除的物品不能借“重新上架”恢复库存；保留原商品的实物链与移除原因。
- 编辑价格/缺陷/照片后，旧报价不得继续按旧条件成交；已生成订单继续使用原快照。
- 草稿、证据和通知旧请求在换账号后不能带新账号令牌提交；共享状态迁移不得丢掉已有保护。
- ES模块的依赖、相对资源、API路径和静态演示子路径必须真实加载；不靠仅检查语法判断迁移完成。

## 0. 已完成的只读基线核验

- [x] 获取origin/main：ad39da0；旧功能分支保留6286861，两者分歧来自bbf7da9后的独立开发。
- [x] 在/tmp/zj-layered-audit导出main临时副本，不改用户运行数据。
- [x] main基线：`python3 -m unittest discover -s tests -v`，55项通过。
- [x] `node tests/frontend_modules.test.mjs`：31模块加载/依赖无环通过。
- [x] 原生客户端隐私、订单展示、密码登录3个Node脚本通过。
- [x] 本机Windows浏览器冒烟结果不冒充本轮验证；整合后仍需执行当前环境可运行的真实浏览器场景。

## 1. 文件职责与迁移映射

| 当前参考功能 | 分层落点 | 职责 |
| --- | --- | --- |
| publishing.py | Backend mission/app/catalog/drafts.py | 私密草稿、版本冲突、发布幂等、表单金额解析 |
| operations.py人员部分 | Backend mission/app/support/accounts.py | 独立客服创建、停用、会话撤销 |
| operations.py信誉部分 | Backend mission/app/support/credit.py | 规则处罚、警告、申诉冲回、受控恢复 |
| operations.py退货部分 | Backend mission/app/support/returns.py | 退回确认、实物链校验、预填重售草稿 |
| notifications.py | Backend mission/app/notifications/service.py | 同事务写通知、账号读/未读、工单收件人 |
| locations.py | Backend mission/app/catalog/locations.py | 候选楼栋常量与公开地点选项，不另建路径推导 |
| 旧草稿/通知表迁移 | Backend mission/app/core/database.py | 增量列/表/索引，保留order_notes、DELETE日志与锁 |
| 商品编辑/筛选 | Backend mission/app/catalog/editing.py、search.py | 分别处理卖家编辑生命周期和查询分页 |
| 装配与HTTP | Backend mission/app/market.py、Backend mission/server.py | 装配领域服务；路由只解析、校验请求并转发 |
| 发布/草稿页面 | web 7M/src/pages/publish.js、drafts.js | 点选发布、继续编辑、草稿箱渲染 |
| 商品管理与筛选 | web 7M/src/pages/listings.js、home.js；components/catalog-filters.js | 管理页、搜索结果、筛选展示 |
| 写入动作 | web 7M/src/actions/catalog.js、publishing.js、inbox.js、support.js | 表单/按钮行为；通过统一委托注册 |
| 通用组件与状态 | web 7M/src/components/publish-form.js、locations.js；core/state.js、http.js、nav.js | 共享表单、地点、唯一可变状态、会话保护、重绘钩子 |
| 通知页面/同步 | web 7M/src/pages/messages.js；core/inbox.js | 接入原会话页，前台轮询/浏览器提醒不引入另一份登录态 |
| 原生客户端 | web 7M/miniprogram/pages及公共工具 | 同步草稿/售后/通知/地点能力，保留用户目录 |

新增文件按职责保持小模块；不机械追求固定文件数，不把原大文件改名成service后继续堆积。

### Task 1: 分层后端功能整合与数据兼容

**Files:** 上述后端领域文件、Backend mission/manage_trial.py、tests/test_publishing.py、test_operations.py、test_notifications.py及对应HTTP测试。

**Interfaces:** 保留Market.save_draft(user_id,payload)、publish_draft(user_id,id,version)、relist_draft(user_id,product_id)、create_support(admin_id,payload)、apply_penalty(...)、reverse_penalty(...)、notifications(user_id,before=0)等现有合同；保留main的my_products、set_product_status、update_order和订单留言。publish继续接受电子产品，并支持草稿发布所需的同事务内部调用。

- [x] 写迁移回归：电子产品发布、付款前改单/留言与草稿重售能在同一Market实例中共存；新旧数据目录升级保留账号、图片、order_notes和原账务；错误地用演示库开启trial仍拒绝。
- [x] 先运行相应测试，记录缺少的服务/字段/API造成的失败；不删除main已有测试来换旧测试。
- [x] 将6286861服务按映射迁入，统一异常与校验来自app/core/errors.py，路径仅导入config；合并表迁移，不把WAL设置带回。
- [x] 在事务内区分seller_delist、refund_removed、credit_block和legacy_unknown等移除原因；无法判断的历史记录进入核对，不能无条件恢复库存。
- [x] 运行Python完整套件，逐项核对main和旧功能分支场景的并集；通过后提交后端整合。

### Task 2: 前端ES模块与原生功能整合

**Files:** 映射中的网页/原生文件、web 7M/src/router.js、main.js、actions/index.js、tests/frontend_modules.test.mjs及草稿/通知/试用浏览器测试。

**Interfaces:** core/http.api(path,data,options={background:false})保留默认代次检查，允许同账号草稿/通知后台同步；state持有token、me、cart、draftEditor和inbox状态。nav继续注册render回调，不由页面import router。

- [x] 写真实浏览器失败场景：用户的新商品频道仍可用；旧账号草稿恢复三图；独立客服处理退货并重售；消息红点和公共地点仍可用；换账号旧操作不得提交。
- [x] 将旧HTML与动作按职责迁移，沿用户现有样式/插画/Logo，不整体替换pages或恢复全局脚本；新动作在actions/index.js中注册，页面不偷偷重复安装全站监听。
- [x] 保留listings路由，并兼容旧selling链接；加入drafts、publish/id等必要路由及静态只读守卫；启动顺序不改坏public-demo注入。
- [x] 更新原生文件与测试引用到web 7M/miniprogram，保留可运行入口；真机/工具未执行结果明确记录。
- [x] 运行模块自检、全部相关Node脚本、真实浏览器及静态子路径演示；通过后提交前端整合。

### Task 3: 原地编辑与可靠下架/恢复

**Files:** catalog/editing.py、catalog/service.py、core/database.py、server.py；前端pages/listings.js、pages/publish.js及actions/catalog.js；Create tests/test_catalog_editing.py。

**Interfaces:** edit_product(user_id,product_id,version,fields)；GET /api/product/edit?id返回本人可编辑DTO与version；POST /api/product/edit接收{id,version,fields}。fields沿用草稿表单的元字符串和图片ID，服务端严格转换为分并复用发布校验。原/api/product/status保持兼容，状态检查进入同一事务。

- [x] 写失败测试：别人的商品不能改；两个版本冲突返回409；reserved/sold不可直接编辑；三图、金额、低分限制不被绕过；不同请求键的下单与编辑/下架竞争只产生有效状态。
- [x] 给商品增加version，编辑时CAS校验最新状态，保留stock_key；报价记录绑定商品版本，价格/关键描述/图片变更时使未锁定报价失效。
- [x] 为已生成订单保留完整快照；不能让普通恢复按钮绕过退货、欺诈或较新实物出售记录。
- [x] 网页管理页按原分组增加编辑入口与明确不可编辑原因；原生按相同合同适配，不复制一套判断规则。
- [x] 运行Python与真实双账号编辑—下单—下架/恢复流程，核对原订单、报价和账务；通过后提交。

### Task 4: 多条件筛选与稳定翻页

**Files:** catalog/search.py、core/database.py、server.py；components/catalog-filters.js、pages/home.js、actions/catalog.js、core/state.js；Create tests/test_catalog_search.py及浏览器筛选场景。

**Interfaces:** 保留旧/api/products的数组合同；新GET /api/products/search使用q/category/college/major/course/edition/condition/delivery/min_price/max_price/sort/cursor/page_size，金额为整数分，返回{items,next_cursor,has_more}。page_size默认20、最大50；未知字段提供明确unknown选项。

- [x] 写失败测试：组合条件、未知版次、免费书、electronics不显示教材专属项；500件数据中匹配项不因旧100件截断丢失；同价按id稳定排序，游标绑定条件，不能跨查询复用。
- [x] 把筛选放在分页之前，以参数化查询及必要索引执行；按所选自提/送货总价排序；游标带排序键和初始最大id，新增商品留到刷新显示。
- [x] 页面共享筛选只在state，更新筛选重置游标；已显示ID去重。商品价格被卖家修改时刷新结果，下单仍以确认的商品/订单快照为准，不承诺跨编辑的永久搜索快照。
- [x] 按category显示筛选抽屉；数据不全可选未知，不逼卖家填写全部课程信息；用户可清空/分享当前筛选。
- [x] 验证移动端筛选、排序与标价口径、翻页新增数据、清空筛选；通过后提交。

### Task 5: 并集回归、独立审查与分层交付包

**Files:** scripts/build_public_demo.py、scripts/build_trial_package.py、README、docs操作/升级记录、启动脚本和回归测试。

- [x] 从新分层目录构建完整源码ZIP，解压后启动；不能缺app子包、ES模块树、Logo或electronics资产，不能带数据库/上传/备份/原始学生表。
- [x] 在旧main格式及6286861格式的临时数据副本分别做升级验证，账号、订单、账务、照片、草稿/通知和order_notes保持可读；失败时不操作原数据。
- [x] 执行Python全套、动态模块加载/无环、Node客户端、两账号浏览器、375/390/768/1440布局、静态子路径无写入检查；按真实执行记录结果，不承诺固定测试数量。
- [ ] 完成本分支整体独立审查，修复重要问题并验证。未运行的Windows/微信原机、公网/支付验收单列。
- [ ] 提交并推送分层集成功能分支，保留main和旧功能分支；交付可运行ZIP、更新说明和第一批实际完成清单，不把后续阶段宣称完成。

## 后续批次保留

第2批客服未读/提示音、退款三级执行及逐件售后；第3批社区/运营/隐私与资格预览后的自动恢复；第4批30人混合容量、恢复和公网模拟试用。微信审核和真实支付各有外部条件，未接入前维持模拟。它们仍在整体方案中，不因本计划聚焦第一批而取消。

## 自查与执行方式

本计划保留用户目录和功能，补齐两分支迁移前置任务，并把并发、快照、权限、实物链、旧请求和静态导出归到具体测试。没有设置未验证的上线日期或购买动作。

推荐：在当前会话由主助手逐项实现，最后做一次独立代码审查；相较每项另开执行/审查代理，减少重复上下文成本。按实施计划技能，计划完成后先交用户审阅，再进入执行。
