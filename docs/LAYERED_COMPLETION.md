# 转角分层整合与商品管理交付

本轮基于用户 `ad39da0` 的分层代码，整合旧功能分支 `6286861` 的草稿、客服、信誉、退货和通知。保留电子产品频道、原视觉/Logo资源、主动下架、付款前改单和订单记录。没有恢复根目录平铺业务文件。

## 本轮完成

- 后端领域分别在 `Backend mission/app/{account,catalog,trade,community,support,notifications,ops}`；路径、数据库和校验在 `core`，`market.py` 负责装配，`server.py` 只分发HTTP。
- 网页在 `web 7M/src/{core,components,pages,auth,actions}`；共享状态统一在 `core/state.js`，重绘经 `core/nav.js`；新增小程序商品查询、编辑、订单动作分别进入 `miniprogram/features/`。
- 三步点选发布：物品/书况、三张实拍、价格/交付。笔记、缺页、附件、成色和版次有默认待核对选项；已知缺陷必须说明。电子产品保留。
- 私密发布草稿：文本本机缓存和服务端自动保存；图片上传后可恢复；30天保留、版本冲突提示、另存；账号切换不会借用新令牌提交旧内容。
- 原地商品编辑：本人在售或主动下架商品可编辑；编辑修改先存本机，点击“保存商品修改”才提交。版本冲突拒绝覆盖；修改与下单在事务内检查最新状态；订单快照不随编辑重写，旧未绑定报价失效。编辑缓存不跨设备同步。
- 主动下架后可恢复；低于60分、交易限制、售后移除和原因不明的历史状态不能借恢复按钮绕过。仅退款不恢复实物；退货确认、模拟退款完成后可生成预填重售草稿，实物链保持唯一。
- 组合筛选：学院、专业、课程、版次、成色、交付和价格。允许未知版次、免费书；送货按含费总价，自提按物品价；查询先筛选再分页，避免旧100条截断。默认20件、最多50件，游标绑定查询；新增商品刷新显示，客户端翻页按ID去重。卖家改价期间的跨页结果不是永久快照。
- 独立客服账号、启停/撤销会话、认领/转派、私密证据、退货记录、规则扣分与申诉冲回已迁入新架构。客服可以建议退款，管理员批准模拟退款，群管理员没有资金和信誉权限。
- 站内订单/售后未读通知、消息中心和可选浏览器提醒已迁入；浏览器提醒仅页面运行时尝试，关窗/手机后台不保证送达，未接微信订阅消息。候选楼栋和自由填写公共地点保留。
- 分层源码打包脚本、静态演示整树导出、Linux Chromium回归和原生客户端逻辑验证均可从项目根运行。

## 新接口与兼容

保留原 `/api/products` 数组合同和原支付、订单、工单接口；本轮不同时迁移FastAPI或改变全部返回封套。后续统一API版本仍需独立迁移客户端。

| 接口 | 合同 |
|---|---|
| `GET /api/product/edit?id=...` | 本人可编辑商品的 `{id,version,fields,photos,simulation}`；金额字段为元字符串 |
| `POST /api/product/edit` | `{id,version,fields}`；完整字段和至少三张本人图片；返回商品DTO |
| `POST /api/product/status` | `{id,action:"delist"或"relist"}`；事务内检查所有权、库存和账号限制 |
| `GET /api/products/search` | `{items,next_cursor,has_more}`；价格条件为整数分 |

筛选参数：`q,category,college,major,course,edition,condition,delivery,min_price,max_price,sort,cursor,page_size`，可附 `seller,favorite,free`。排序 `newest/price/price_asc/price_desc`。未知信息使用 `unknown`；`free=1`按物品价为0查询，送货费仍单独展示。

## 启动与升级

1. 安装Python 3.12，运行 `python -m pip install -r "Backend mission/requirements.txt"`。
2. 新目录完整解压，双击 `start-trial.bat`；或运行 `python "Backend mission/server.py" --trial --port 8080`。
3. 保持窗口运行，本机浏览器打开 `http://127.0.0.1:8080`。端口冲突可用8081脚本，启动器不会强制结束其他进程。
4. 管理员在本机终端单独创建：`python "Backend mission/manage_trial.py" create-admin --data "原试用数据目录"`。按提示输入手机号和独立密码；客服可由管理员网页创建或 `create-support`。

**有旧数据时**：停止服务，先备份原 `var-trial/` 和图片。用原数据的副本试升级，再运行 `python "Backend mission/server.py" --trial --data "原试用数据目录"`。不要混用演示库、不要删除原数据库；不要只替换server.py。升级增加列/表和索引，保留DELETE日志模式、订单留言与账务。历史移除原因无法确认时保守标记 `legacy_unknown`，需人工核对。

源码包不携带账号、上传、数据库、备份或原学生表。还没有真实公网服务；本机地址只能本机访问，真机小程序不能使用电脑的127.0.0.1。

## 验证入口

```bash
python3 -m unittest discover -s tests -v
node tests/frontend_modules.test.mjs
node tests/frontend_session.test.mjs
node tests/frontend_cache.test.mjs
# 逐个运行 tests/native_*.test.js
python3 tests/layered_browser_smoke.py
python3 tests/public_demo_smoke.py
python3 tests/ui_redesign_smoke.py
python3 tests/package_smoke.py
python3 scripts/build_trial_package.py --output /tmp/zhuanjiao-trial.zip
```

浏览器脚本在临时数据库运行。旧数据迁移对照需要Git历史中的 `ad39da0` 和 `6286861`；纯源码ZIP无历史时该项明确跳过。Pillow、Playwright和Chromium是本环境已验证的开发依赖；没有执行Windows或微信开发者工具/真机验收。

## 后续批次仍保留

本轮是已批准补齐方案的第一批。客服逐工单未读/提示音、退款建议—批准—执行三级记录、逐件售后、社区目录、隐私/统计、30天自动信誉恢复、容量与真实公网部署等继续按原方案排期。本轮没有宣称34项全部完成，也没有接入真实微信支付、自建资金钱包或完成小程序审核。

## 本轮已执行记录

- Python：107项通过，包括两种旧版数据迁移、并发与库存、草稿/客服/信誉/通知、HTTP和打包检查。
- 网页：49个模块真实加载、显式静态依赖图无环；发布晚返回/切换页面保护和挂起草稿的晚上传保护脚本通过。
- 原生客户端：8个Node脚本通过，含编辑版本、金额/查询合同和会话切换；这不是微信工具编译或真机验收。
- Linux Chromium：分层试用8组完整流程、旧完整交易/售后/群聊流程、公开静态子路径/只读检查、原视觉首屏与375/390/768/1440布局检查通过。
- 干净源码ZIP：校验文件哈希、解压、空库试用启动与health/config/search/模块入口请求通过。

独立审查确认的3项P2均已用先失败、后通过的回归修复，见 [独立审查记录](reviews/2026-10-16-layered-review.md)。未确认的Windows/微信真机等范围仍单列。
