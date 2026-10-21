# 项目文件说明

2026-10-18 整理。此次只归档无正式代码引用的本地旧文件、集中存放参考资料并补文档导航；未修改业务代码、数据结构、接口、金额单位、角色或交易规则。

## 2026-10-21 根目录清理

根目录重新变乱的原因不是代码，而是**每轮压测、云端验证、启动器修复都会新生成 `var-*` / `_backup-*` 目录，且没有清理**。其中 `var-load/`（压测快照 + 上传图）已达 178M、`var-cloud/` 未进 `.gitignore`——一旦有人 `git add -A` 就会把数据目录提交进仓库。

本次处理（全部为**移动**，未删除任何文件，可整目录移回）：

| 原位置 | 现状 | 说明 |
| --- | --- | --- |
| `_backup-2026-10-15`、`_backup-d1`、`_backup-docs-20261020`、`_backup-launcher-20261018-114347`、`_backup-rescan-20261018-144913` | → `_local/archive/2026-10-21/` | 5 个历史备份，合计约 9.6M |
| `var-load/` | → 同上 | 178M 压测数据（backups 141M + uploads 35M），今日 14:25 产生 |
| `var-cloud/` | → 同上 | 772K 云端验证副本 |
| `.venv-trial-broken-20261019/` | → 同上 | 30M 损坏的 Python 环境 |
| `_shots/` | → 同上 | 13M 测试截图 |
| `d1out.json`、`_ui_messages.png` | → 同上 | D1 导出与单张截图 |

`.gitignore` 同时补齐两条规则，防止复发：

- `var-*/`：覆盖 `var-load/`、`var-cloud/` 及未来任意 `var-xxx/`；`var/`（演示）与 `var-trial/`（试用）原本已忽略。
- `.wrangler/`：根目录 wrangler 缓存含 `wrangler-account.json` 账号信息，任何位置都不提交。

**根目录当前只应出现**：`Backend mission/`、`web 7M/`、`docs/`、`scripts/`、`tests/`、`downloads/`、`var/`、`var-trial/`、`repair-wheels/`、`tools/`、`.venv-trial/`、`_local/`、`_local-run/`、`start-*.bat`、`README.md`、`UPDATE-WINDOWS.txt`。出现其它 `var-*`、`_backup-*`、`*broken*` 目录时，应直接归入 `_local/archive/<日期>/`，不要留在根目录。

**启动脚本分工（6 个都在用，不是重复入口）**：`start-trial-8081.bat` 常规试用主入口；`start-trial-lan-8081.bat` 局域网访问；`start-mysql-8081.bat` MySQL 数据源；`start-public-8081.bat` Cloudflare 临时隧道；`启动转角.bat` 参数化启动（可传端口与数据目录）；`start-trial.bat` 早期 8080 版本，仅兼容旧习惯。

```text
huali-corner-trial/
├── Backend mission/
│   ├── server.py               HTTP 服务入口与路由
│   ├── manage_trial.py         本机账号管理命令
│   ├── migrate_to_mysql.py     既有迁移工具，不能随手用于真实库
│   ├── requirements.txt        固定业务依赖
│   ├── render.yaml             既有托管配置
│   └── app/
│       ├── market.py           Market 领域组合根
│       ├── seed.py             虚构演示数据，仅演示模式
│       ├── core/              路径、连接、事务、异常
│       ├── account/           登录、资料、头像、信誉辅助逻辑
│       ├── catalog/           商品、图片、上下架、审核入口、报价
│       ├── trade/             订单、账本、订单通知、定时业务
│       ├── community/         帖子、私聊、群聊、客服会话
│       ├── support/           工单、退款处理、信誉处置
│       ├── staff/             人员账号与角色层级
│       ├── moderation/        内容规则与审核
│       └── ops/               对账与一致性备份
├── web 7M/
│   ├── index.html             正式网页入口，加载 src/main.js
│   ├── src/                   core、components、pages、actions、auth
│   ├── assets/                网页素材
│   ├── miniprogram/           原生微信小程序源码
│   └── public-demo.js         只读虚构演示适配
├── scripts/                   启动、演示导出、词库与账号工具
├── tests/                     Python、Node 和浏览器测试
├── docs/                      文档，入口 docs/README.md
│   ├── standards/             开发规范原文及适用说明
│   ├── references/            用户提供资料的来源副本
│   ├── research/              学校目录等资料
│   └── superpowers/           specs 与 plans
├── downloads/                 既有下载制品，不是业务源码入口
├── start-*.bat                兼容现有用户习惯，保留根目录启动入口
├── var/                       演示数据，禁止提交
├── var-trial/                 已有试用数据，禁止删除或提交
├── repair-wheels/             离线依赖，启动器依赖此固定位置
├── .venv-trial/               本地隔离 Python 环境
├── _local-run/                本次后台服务日志，不提交
└── _local/                    本地保留资料，不提交
    ├── legacy-flat/           旧平铺 Python 模块、旧网页 app.js
    ├── startup-repair/        启动修复说明与原 ZIP
    └── organization-manifest.json  原位置、归档位置和 SHA256
```

## 归档原则

归档的 6 个旧后端文件为 `auth.py`、`community.py`、`db.py`、`market.py`、`paths.py`、`seed.py`，以及网页根目录的旧 `app.js`。它们原先均为本地未跟踪文件；正式后端使用 `app.*` 导入，网页使用 ES 模块。原字节内容完整保留，文件移入前后核对 SHA256，没有清除另一位开发者的工作。

归档文件不是第二套可运行应用，不应直接覆盖现有模块。需要取回时按清单逐项复制到另一个目录比较，不要一次性覆盖整个项目。所有带空格路径在终端中必须正确引用。

`app/seed.py` 是正式演示数据模块，与归档的根目录旧 `seed.py` 不同；前者保留。`web 7M/miniprogram/app.js` 是小程序入口，与归档的网页根目录 `app.js` 不同；前者保留。

## 本轮没有强行拆分的模块

通知目前在 `trade/service.py`，SQL schema 与数据库适配目前在 `core/database.py`。若以后拆成 `notifications/`、迁移模块或独立路由模块，需要单独保证导入、事务和 API 兼容；本次不为目录外观制造空模块或搬动运行代码。

整理期间另外检测到 `app/cloudflare/` 新增及 `docs/CLOUDFLARE_ACCESS.md` 更新，属于并行部署工作，已原样保留；上方目录列出已检查的既有主线模块，不代表该适配已完成验收。
