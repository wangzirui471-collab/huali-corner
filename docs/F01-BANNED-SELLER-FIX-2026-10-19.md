# 交付说明：F-01 封禁卖家商品复活缺陷修复（2026-10-19）

分支：`fix/f01-banned-seller-release`（提交 `ae67036`，基于 `fix/auth-client-kdf` @ 09305a5）
不直接推 `master`；未合入任何他人分支，未触碰工作区里其他会话未提交的改动。

## 1. 改了什么

F-01：卖家被封禁后，待付款订单被取消时 `release()` 无条件把商品设回
`available`，商品重新进入公开列表，其他买家仍可下单。修复四路同源问题：

| 位置 | 修复 |
| --- | --- |
| `app/trade/service.py release()` | 按卖家状态恢复库存：`active` 才退回 `available`；被封禁 / 注销 / 停用退回 `removed` 并清 `promoted_until`。增加 `AND status='reserved'` 幂等护栏 |
| `app/trade/service.py checkout()` | 新增卖家 active 校验，不满足返回 409「卖家当前不可交易」 |
| `app/trade/service.py update_order()` | 买家移除商品时套用同一卖家状态规则 |
| `app/trade/service.py tick()` | 30 分钟超时关闭、24 小时未确认自动退款两条路径的释放与通知文案 |
| `app/support/service.py _settle_banned_orders()` | 封禁结算关闭订单时释放规则同上；通知文案按实际恢复结果生成，不再谎称「释放回在售」 |
| `app/catalog/service.py products()` | 公开商品流增加 `u.status='active'` 过滤 |

语义与 Cloudflare 侧 WIP 中已实现的 `cf_trade_release` 对齐（CASE available/removed），
两侧规则一致。事务内查询一律使用事务连接 `c`（`row()` 另开连接读不到未提交数据）。

## 2. 文件清单

- `Backend mission/app/trade/service.py`
- `Backend mission/app/catalog/service.py`
- `Backend mission/app/support/service.py`
- `tests/test_defect_fixes.py`（更新 M4 旧断言 + 新增 5 条 F-01 回归）

## 3. 接口变化

无新增 / 删除接口。行为变化两处：

- `POST /api/checkout`：卖家非 active 时由「下单成功」变为 409「卖家当前不可交易」。
- `GET /api/products`：非 active 卖家的商品不再出现在公开列表（卖家本人的
  「我发布的」`/api/my-products` 不受影响，仍可见自己的已下架商品）。

## 4. 验证结果（2026-10-19 本机实跑）

- `tests/test_defect_fixes.py`：23 项通过（新增 F-01 五条：封禁后 reserved 商品落
  removed、公开列表隐藏、下单 409、超时关闭不复活、active 卖家仍正常释放）。
- 全量 `python -m unittest discover -s tests`：420 项，7 项失败，均为**既有失败**：
  - 6 项在 `tests/test_cloudflare_trade.py`（另一会话未提交的 Cloudflare WIP 自测，
    只依赖 `cloudflare_test_support` 与 `app/cloudflare/*`，与本次同步后端改动无关）；
  - 1 项 `test_trial_launcher`：本机 `TEMP` 为 8.3 短路径（`ADMINI~1`）导致
    `Path.cwd()` 与 `resolve()` 在临时目录不一致，属环境特有问题；真实启动路径
    （`E:\zi\huali-corner-trial`）不受影响，在跑服务即为证明。
- 未运行浏览器冒烟（本轮纯后端改动；前端无改动）。

## 5. 未完成限制

- **在跑的 8081 服务是 10:55 启动的旧代码，不含本修复**；重启
  `start-trial-8081.bat` 后生效。重启前建议先关掉多余的控制台窗口
  （今早 10:55 启动器被运行了两次，现有两条「包装进程→服务」孤儿链，
  两个服务同时监听 8081）。
- 24 小时自动收货、支付、退款等流程只有单测与历史 browser smoke 记录，
  未在用户 Windows 实机做完整回归。
- Cloudflare WIP 的 6 个失败测试交给负责该部分的会话处理；本修复未改
  `app/cloudflare/*`。

## 6. 数据迁移与回滚

- 无 schema 变更、无数据迁移。修复只改状态流转逻辑。
- 回滚：`git revert ae67036` 或切回 `fix/auth-client-kdf` 即可，
  不影响任何已存数据；已按新规则落到 `removed` 的商品，解封后由卖家
  在「我发布的」自行重新上架。
- 真实数据已备份：`var-trial/backups/manual-20261019-1120/`
  （SQLite 一致性快照 + uploads + moderation）。
