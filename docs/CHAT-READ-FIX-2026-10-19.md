# 聊天发送重复、页面跳转与已读回执修复（2026-10-19）

线上地址：https://zhuanjiao.wangzirui471.workers.dev
部署版本：`a97fbae9-f44c-4a63-ac9f-93a4517350de`（前一次为 `66f8e74b`）

## 一、用户报告的现象

1. 所有页面切换都卡顿（首页、聊天、客服等）。
2. 聊天里发完消息会「跳到别的页面」，并且同一条消息出现两次甚至更多。
3. 需要已读功能：群聊显示「几人已读 / 全部已读」。

## 二、根因（已复现，非推测）

在本地隔离实例上用 5 秒网络延迟（对齐 workers.dev 实测 TTFB ≈ 5.4s）复现：

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 点一次发送 | 1 个 POST，界面 **3 条**重复气泡 | 1 个 POST，1 条 |
| 连点两次发送 | 2 个 POST，6 条气泡 | 1 个 POST，1 条 |
| 连按两次回车 | 2 个 POST，6 条气泡 | 1 个 POST，1 条 |

结论：

- **重复显示**：消息轮询是 `setInterval` 每 3 秒一次，而一次拉取要 5 秒。
  请求重叠后，两批**相同**消息各自追加一次；前端既没有并发合并，也没有按
  消息 id 去重。
- **真的发两条**：发送按钮没有「发送中」锁，慢网络下用户看不到反馈会连点，
  每次都用新的幂等键，服务端的 `request_key` 唯一约束拦不住。
- **跳到别的页面**：输入区原来是 `<form>`，一旦本地 submit 监听没生效
  （页面数据未就绪、脚本异常等窗口期），浏览器会执行**原生提交**，
  地址变成 `/?message=…`，SPA 丢掉 hash 回到首页。
- **卡顿观感**：页面都要等接口回来才 `shell()` 绘制，这段时间屏幕上没有任何
  变化；再加上后台标签页仍在轮询，多个页面互相抢带宽。

## 三、改动

### 前端

| 文件 | 改动 |
| --- | --- |
| `web 7M/src/pages/messages.js` | 输入区由 `<form>` 改为 `div#wx-composer`，发送只走显式调用，**不存在原生提交路径**；发送中锁按钮 + 复用同一幂等键；乐观气泡（发送中/已发送/失败标红并回填正文）；`pullNew` 并发合并 + 按 id 去重 + 摘掉对应乐观气泡；已读回执渲染与刷新；后台标签页停止轮询；回执 9 秒刷新一次 |
| `web 7M/src/pages/messages.js` | 通知条目可点击跳转（工单/商品/订单/帖子/客服/诚信页），帖子类跳社区并展开该帖评论 |
| `web 7M/src/core/progress.js`（新增） | 路由切换顶部进度条，点击即出现，页面画完收起，15 秒兜底 |
| `web 7M/src/core/nav.js` | `go()` 里点亮进度条 |
| `web 7M/src/router.js` | 渲染开始/结束（`finally`）开关进度条，只有最后一次渲染能收 |
| `web 7M/market.css` | 进度条、已读回执、乐观气泡样式 |

### 后端（同步版）

| 文件 | 改动 |
| --- | --- |
| `app/community/service.py` | 新增 `message_receipts()`；`content_action` 的帖子移除通知补 `post_id` |
| `server.py` | 新增 `GET /api/messages/receipts?room_id=` |
| `app/trade/service.py` | `notify()` 支持 `product_id`；通知查询带上该列 |
| `app/catalog/service.py` | 商品下架/复核通知带 `product_id` |
| `app/core/database.py` | notifications 表加 `product_id`（SQLite/MySQL 建表 + 启动迁移补列） |
| `tests/test_message_receipts.py`（新增） | 3 条回执语义回归 |

### 后端（Cloudflare Worker）

| 文件 | 改动 |
| --- | --- |
| `app/cloudflare/community_api.py` | 新增 `cf_message_receipts` 与 `/api/messages/receipts` 路由 |

## 四、已读回执的语义

- 数据源是 `members.last_read_id`（拉取消息时前移），不新增表、不写新状态。
- `GET /api/messages/receipts?room_id=` 返回：
  `{"total": 3, "readers": [{"user_id":2,"last_read_id":12,"nickname":"…"}]}`
  `total` 只数「除自己以外」的成员。
- 前端按 `reader.last_read_id >= 消息 id` 判定这条消息被谁读到：
  群聊显示 `2/3 已读`、全部读过显示 `全部已读`；私聊显示 `已读` / `未读`。
- 轮询会刷新回执，所以别人刚读，旧气泡上的数字也会跟着变。

## 五、验证

- 本地隔离实例（`_local/uitest`，真实库副本 + 测试账号），Chrome 无头：
  - 5 秒延迟下三种发送方式均为 1 个 POST、1 条气泡（修复前 3～6 条）。
  - 已读回执联动：`0/3 已读` → 对方拉取后 `1/3 已读`。
  - 首页/社区/我的/聊天逐页可达，进度条出现后能收起，无 JS 报错。
- 后端全量 `python -m unittest discover -s tests`：425 项，7 项失败，
  全部是既有失败（6 项 `test_cloudflare_trade` 的 WIP 用例、1 项本机 TEMP
  8.3 短路径导致的启动器用例），与本次改动无关；新增 3 项回执用例通过。
- 前端模块自检：47 个模块可加载、依赖无环。
- `wrangler deploy --dry-run` 通过，已部署两次并核对线上资源：
  `/src/pages/messages.js` 含回执与去重逻辑、无 `wx-form`；
  `/src/core/progress.js` 可访问；`/api/messages/receipts` 未登录返回 401
  （路由存在，非 404）。

## 六、限制与后续

- **浏览器缓存**：线上是 ES Module，改完要硬刷新（Ctrl+F5）才会加载新脚本。
- 网络到 workers.dev 的 RTT 本身没有变，进度条只是把「等待」变得可见；
  真正的速度提升需要绑定自定义域名（走更近的节点）或改用国内可达的部署。
- 已读位点是「会话级」的：成员只要拉取过消息就算读到，不区分是否滚动到该条。
  这与主流 IM 的「进入会话即已读」一致，但不是「逐条曝光」。
- 本次改动未提交 git：工作区还有另一会话未提交的 Cloudflare/前端改动，
  整文件暂存会把对方未完成的改动一起提交，需要先对齐再分文件提交。
- 线上登录态流程（真实账号收发消息）尚未由本机验证，需要用户端硬刷新后确认。

## 七、回滚

- 代码：`git checkout -- "web 7M/src/pages/messages.js" "web 7M/src/router.js" "web 7M/src/core/nav.js" "web 7M/market.css"`，
  删除 `web 7M/src/core/progress.js`；后端回退 `community/service.py`、
  `server.py`、`trade/service.py`、`catalog/service.py`、`core/database.py`。
- 线上：`wrangler rollback`（或指定上一个版本 `66f8e74b`）。
- 数据库：`product_id` 只是新增可空列，回滚代码后保留无副作用；
  回执接口只读，不产生数据变更。

## 八、访问不了（ERR_CONNECTION_CLOSED）的排查记录（同日 18:5x）

用户反馈 `https://zhuanjiao.wangzirui471.workers.dev/#community` 打不开。结论：**站点正常，是本机 DNS 被 VPN 劫持**。

证据：

| 检查 | 结果 |
| --- | --- |
| 外部网络抓取首页 / `/api/config` | 均 200，返回正常 HTML / JSON |
| 线上 `/src/core/progress.js` | 可读，含 `startProgress`（说明新版本已生效） |
| 本机 `nslookup` 该域名 | `198.18.0.12`（假 IP，198.18.0.0/15 是 fake-ip 段） |
| 换 120.80.88.88、223.5.5.5 查询 | 仍返回 `198.18.0.12`（说明 DNS 查询被 TUN 拦截） |
| DoH（1.1.1.1）查询 | `172.67.138.179` 等真实 Cloudflare 地址 |
| 用真实边缘 IP + 正确 SNI 直连 | 200，TLS 0.4s |
| 进程/网卡 | `PulseVPN`、`PulseVPNCore` 运行中，`PulseVPN Tunnel` 状态 Up，DNS 为 198.18.0.2 |

处置：在 `C:/Windows/System32/drivers/etc/hosts` 固定域名到 Cloudflare 边缘节点
（原文件已备份为 `hosts.bak-20261019`）：

```
104.16.0.1 zhuanjiao.wangzirui471.workers.dev
```

处置后实测：

- `curl` 首页 200，TTFB 从 5.4s 降到 0.41s。
- 真实浏览器打开 `#community`：2.9s 完成加载，4 条帖子，无 JS 报错、无失败请求。
- 页面切换：community 1.25s（首次）/ 0.36s，home 0.38s。
- `/api/products` 1.53s（Worker 冷启动），静态资源 0.42～0.47s。

这也解释了此前的「所有页面切换都卡顿」：请求走的是这条坏掉的 fake-ip 路径，
每个请求 TLS 都要重试，固定后单请求从 5.4s 降到 0.4s 量级。

注意：hosts 只影响本机；其他设备要么关掉同类 VPN，要么做同样处理。
彻底方案是给 Worker 绑自定义域名（当前账号下没有 zone），或换一个可用节点。
