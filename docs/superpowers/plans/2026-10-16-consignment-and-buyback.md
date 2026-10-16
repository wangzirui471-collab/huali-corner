# 毕业季托管寄卖 + 教材集采回收 · 设计方案（待确认）

> 状态：**方案，未开工**。本文档只做设计，等你确认第 7 节的四个决策后再动代码。
> 前置：commit `ceb0928`，工作区干净。

---

## 0. 先说冲突：这两个功能需求文档明确排除过

动工前必须解决，否则做完了在文档层面是「超范围实现」。

| 出处 | 原文 | 与本方案的关系 |
|---|---|---|
| §2.3（第 120 行） | 「首期不做**自营回收**、验机鉴定、充值钱包、贷款、高价奢侈品鉴定、跨校物流体系。」 | **教材集采回收 = 自营回收**，被直接排除 |
| §13（第 651 行） | 「用户希望买家付款后，确认收货再让卖家获得货款。该目标应通过具备相应能力和资格的支付服务实现，**不能简单把真实资金收进个人账户，再声称软件提供担保托管**。产品不建设可充值或提现的自有钱包。」 | **托管寄卖的「平台代收 + 延迟结算给寄卖人」= 担保托管的形态** |

**为什么本项目仍然可以做**：本站是**模拟交易，无真实资金**（§9.4 已要求「所有相关页面和记录标明模拟」）。没有真实资金流入平台账户，就不存在 §13 说的资金归集问题，也不涉及支付牌照。

**但必须同时锁死三条边界，否则就是拿模拟机制去暗示真实能力：**

1. 全部环节标注「模拟」，不得出现任何收款码、转账指引、垫资承诺。
2. **不建**钱包表、余额表、充值、提现。寄卖人看到的是「本笔寄卖已结算 ¥X（模拟）」，是**流水记录**，不是可支配余额。
3. 不承诺资金安全、不出现「平台担保」「资金托管」字样，改用中性表述：「平台代为展示与交付，款项在模拟账务中结算」。

**建议**：需求文档升到 **v1.3**，在 §2.3「后续探索」里把这两个功能挪进来，标题写成「**模拟演练**：毕业季托管寄卖、教材集采回收」，并在 §13 补一句「本试点不接入真实资金，托管与回收均为模拟记录，不代表平台提供真实资金担保」。

---

## 1. 地基：平台自营身份

两个功能共用一个前提——**平台自己得是一个能挂商品的"卖家"实体**。现在没有。

现状：`users.role ∈ {user, support, admin}`，全部是自然人。`products.seller_id` 指向 `users.id`，所以平台要卖东西，就得有一条平台自己的 users 记录。

### 方案：系统保留账号

```
role = 'platform'
phone = '10000000000'      # 刻意用不合法号段
nickname = '转角自营'
```

**为什么手机号故意非法**：`AccountService._phone()` 的正则 `1[3-9][0-9]{9}` 不匹配 `1[0-9]...`，所以这个号码**无法通过注册接口占用，也无法通过登录接口登录**。它只能由启动流程直接 INSERT 进库。这条设计同时挡住了两件事：真人抢注这个号，以及有人拿这个号登录。

**权限上要显式排除**：`staff()` 只认 `support`/`admin`，`platform` 不在其中——自营账号不能进后台。

**需要改的地方**：

| 位置 | 改动 |
|---|---|
| `app/market.py` `__init__` | demo 模式的 `INSERT OR IGNORE INTO users` 列表加一条 platform；trial 模式同样补一条 |
| `app/core/database.py` | `products` 加一列 `origin TEXT DEFAULT 'peer'`（沿用文件里既有的 `PRAGMA table_info` + `ALTER TABLE` 补列模式，老库自动迁移） |

`origin` 取值：

- `peer` —— 同学之间交易（现有全部商品，默认值）
- `consignment` —— 托管寄卖上架
- `buyback` —— 教材回收后转成的自营库存

**为什么加列而不是靠子表反查**：`products()` 是主页/搜索/详情的高频路径，为了打个「自营」角标去 JOIN 两张表不划算；一列 `origin` 直接跟着商品走，且能顺手支持筛选。

---

## 2. 毕业季托管寄卖

### 2.1 业务流程

```
学生提交寄卖申请
      ↓  （线下）平台验货、定价、入库
平台受理 → 上架为 origin='consignment' 的商品（seller_id = 平台）
      ↓
买家正常下单付款  ←── 完全复用现有 checkout / order_action / 订单状态机
      ↓
订单 completed → 平台扣佣金 → 余款记为「寄卖人已结算」（模拟流水）
      ↓
到期未售出 / 寄卖人申请退回 → 线下退还，商品下架
```

**关键：买家侧零改动。** 托管商品就是一条普通商品，买家体验和买同学的二手书完全一致，走同一套订单状态机。所有托管特有的逻辑都发生在「上架前」和「成交后」两个端点。

### 2.2 数据模型

```sql
CREATE TABLE consignments(
  id INTEGER PRIMARY KEY,
  owner_id INTEGER NOT NULL,     -- 寄卖人（真实学生）
  product_id INTEGER,            -- 上架后关联的商品；上架前为 NULL
  title TEXT, category TEXT,
  expected_price INTEGER,        -- 寄卖人期望到手价（分）
  list_price INTEGER,            -- 平台挂牌价（分）
  commission_rate INTEGER,       -- 佣金，万分比；1000 = 10%
  payout_amount INTEGER,         -- 实际结算给寄卖人的净额
  delivered_at REAL, listed_at REAL, expires_at REAL, settled_at REAL,
  status TEXT DEFAULT 'submitted',
  note TEXT, staff_id INTEGER, created REAL
);
```

`status` 状态机（七态，全部单向）：

```
submitted  待验货   ─┬→ received  已入库 ─→ listed  已上架 ─┬→ sold    已售出 ─→ settled 已结算
                     │                                      └→ returned 已退回
                     └→ rejected  未通过（成色不符/疑似盗版）
```

### 2.3 账务怎么记（这是最容易记错的地方）

`ledger` 表有约束 `UNIQUE(order_id, kind)`。托管订单成交时要处理两笔钱，分开放：

| 钱 | 记在哪 | kind |
|---|---|---|
| 买家付款 | `ledger` | `payment`（现有） |
| 平台作为卖家的结算 | `ledger` | `settlement`（现有） |
| **平台佣金** | `ledger` | `service_fee`（**新 kind**） |
| **付给寄卖人的净额** | `consignments.payout_amount`（**不入 ledger**） | — |

**为什么寄卖结算不写 ledger**：`ledger` 的语义是「**订单托管资金**的进出」。买家付的 `total` 全额归平台（平台是这单的卖家，`settlement = total`）；平台再转给寄卖人的那笔钱是**平台与寄卖人之间的往来**，不在这张订单的资金闭环里。硬塞进 ledger 会让 `reconcile()` 的公式失去意义。

好在这笔账**有地方可查**：`consignments.payout_amount + settled_at + commission_rate` 就是完整凭据。

`service_fee` 作为新 kind 不会撞 `UNIQUE(order_id, kind)`（kind 不同），无需改表结构。

**结算公式**：

```
payout_amount = subtotal × (10000 - commission_rate) ÷ 10000     # 以商品小计为基数，不含运费
```

用**小计**而非总额作基数：运费是平台实际跑腿成本，不该被抽佣。

### 2.4 必须改的现有代码

| 文件 | 改什么 | 风险 |
|---|---|---|
| `app/trade/service.py` `complete()` | 订单完成时，若 items 里含 `origin='consignment'` 的商品，写 `service_fee` 并回填 `consignments` | **中**：`complete()` 被 `receive` 和 `tick()` 两处调用，两处都要覆盖 |
| `app/ops/service.py` `reconcile()` | 现有公式 `held = payment - refund - net_settlement` 不含佣金。需在输出里**单独列出** platform_revenue / consignment_payout，否则对账表看着平、实际少了钱 | **中**：改公式容易改错，必须有测试兜底 |
| `app/support/service.py` `check_conflict()` | 见下方专项风险 | **高**（业务风险，非技术风险） |
| `server.py` | 新增 3 条路由 | 低 |

### 2.5 专项风险：平台既是卖家又是裁判

自营商品的纠纷里，平台是**当事方**。现有 `check_conflict()` 的两条防线都挡不住：

- `if t['product_id']: require(self.product(pid)['seller_id'] != u, ...)` —— 自营商品的 `seller_id` 是 platform 账号，**不是** admin 本人，这个判断会**静默放行**。
- `if t['order_id']: require(u not in [buyer_id, seller_id])` —— 同理，`seller_id` 是 platform。

于是管理员可以裁决自己平台自营商品引发的纠纷，且没有任何提示。

**处理办法**（代码 + 文档双管）：

1. 代码：`check_conflict()` 遇到 `origin != 'peer'` 的商品时，不再静默放行，而是要求调用方显式确认——例如 `resolve_ticket` 对自营工单**只允许** `outcome ∈ {refund, reject}`，**禁止** `resolved`（即不允许平台单方面"判自己赢"）。
2. 文档：§13 补一句「平台自营商品的纠纷默认退回/退款，不由平台单方裁决归属」。

### 2.6 接口与界面

```
POST /api/consign             提交寄卖申请（学生）
GET  /api/consignments        我的寄卖列表（学生）
POST /api/consign/review      平台受理：accept/reject/receive/list/return（staff only）
```

界面：

- 发布页加「毕业季托管寄卖」入口 → 独立页 `web 7M/src/pages/consign.js`
- 「我的」加「我的寄卖」入口
- 管理端工作台加「寄卖队列」（现在工作台是 `server.py` 里 `/api/admin` 拼的，需要加一段）
- 商品卡片 + 详情页加「自营 · 平台已验收」角标（数据源就是 `products.origin`）

---

## 3. 教材集采回收

分两段：**回收**（平台向学生收书）+ **集采**（平台向学生卖书）。两段可以独立上线。

### 3.1 回收段

```
学生提交回收申请（教材版次 / ISBN / 成色 / 数量）
      ↓
平台按规则报价（模拟估价）
      ↓
学生接受 → 线下交书 → 平台确认收货 → 记一笔「平台付给学生的回收款」（模拟）
      ↓
书入库，成为 origin='buyback' 的商品
```

```sql
CREATE TABLE buybacks(
  id INTEGER PRIMARY KEY, seller_id INTEGER,
  title TEXT, isbn TEXT, edition TEXT, publisher TEXT, condition TEXT,
  quantity INTEGER DEFAULT 1,
  quoted_price INTEGER, accepted_price INTEGER,   -- 单本，分
  status TEXT DEFAULT 'quoted',
  -- quoted 待确认 / accepted 已接受 / received 已收货 / paid 已付款 / rejected / cancelled
  created REAL, received_at REAL, paid_at REAL, staff_id INTEGER, note TEXT
);
```

**资金方向与托管相反**：这里是**平台付钱给学生**。同样只在 `buybacks` 表里记流水，不入 `ledger`（不是订单资金）。**不建钱包余额**，学生看到的是一条「已收款 ¥X（模拟）」记录。

### 3.2 集采段

```sql
CREATE TABLE collectives(
  id INTEGER PRIMARY KEY, title TEXT, isbn TEXT,
  price INTEGER,                 -- 集采价（分）
  target_qty INTEGER,            -- 起订量
  stock_cap INTEGER,             -- 库存上限（回收来的实有册数）
  deadline REAL, status TEXT DEFAULT 'open',
  -- open 预约中 / formed 已成团 / failed 已流团 / closed 已结束
  created REAL, note TEXT
);

CREATE TABLE collective_orders(
  id INTEGER PRIMARY KEY, collective_id INTEGER, user_id INTEGER,
  quantity INTEGER DEFAULT 1, status TEXT DEFAULT 'reserved',
  -- reserved 已预约 / converted 已转订单 / cancelled 已取消
  created REAL, order_id INTEGER,
  UNIQUE(collective_id, user_id)
);
```

**成团 / 流团由现有 timer 驱动**：`server.py` 已经有 30 秒一轮的 `timer()` 线程（在跑 `market.tick()`），在这里挂一个 `collective_tick()` 即可，不需要新机制。

**预约是否收款：建议不收。** 收定金要引入「定金退还 / 违约没收 / 部分退款」一整套状态，复杂度陡增，而这是个模拟演练。**纯登记**：预约不产生任何账务，成团后学生自己点「去下单」，走现有 `checkout`。

**超卖是个真问题**：回收来 5 本、集采 10 人成团 → 库存不够。因此 `target_qty` 必须同时受 `stock_cap` 约束，成团判定为：

```
参与人数 ≥ target_qty  且  参与人数 ≤ stock_cap
```

**成团后怎么下单**：现有 `checkout` 是按 `product_ids` 下单，所以成团时需要先为批次绑定一条平台库存商品，再由学生各自下单。或者更省事：**成团即由平台批量生成订单**（卖家是平台，买家是各预约人），直接复用 `checkout` 内部逻辑。两种都可行，我倾向前者——学生自己确认一次更符合「不代扣款」的基调。

### 3.3 界面

- 社区页「求购」旁加「教材集采」入口
- 独立页 `web 7M/src/pages/collective.js`（批次列表 + 预约 + 进度条）
- 回收申请页 `web 7M/src/pages/buyback.js`
- 管理端加「回收队列」「集采批次管理」

---

## 4. 改动清单汇总

| 文件 | 改动 | 风险 |
|---|---|---|
| `app/core/database.py` | 新增 4 表（consignments / buybacks / collectives / collective_orders）；`products` 补 `origin` 列 | 低 |
| `app/market.py` | 启动创建 platform 账号（demo + trial） | 低 |
| `app/catalog/service.py` | `publish` / `product` 带出 `origin`；`my_products` 支持按 origin 筛 | 低 |
| `app/trade/service.py` | `complete()` 触发托管结算 | 中 |
| `app/ops/service.py` | `reconcile()` 纳入平台佣金与自营往来 | 中 |
| `app/support/service.py` | `check_conflict()` 自营商品利益冲突显式处理 | **高** |
| `server.py` | 新路由 + 集采定时任务 + 管理端数据 | 低 |
| 前端 | 4 个新页面 + 入口 + 角标 | 中 |
| `docs/转角软件需求文档-v1.2.md` → v1.3 | 范围与合规表述 | 低 |

**回归高危点**：`complete()` 和 `reconcile()`。前者被自动收货定时任务调用，后者是资金正确性的唯一出口。两处都必须有「托管订单完成后 `held==0`」的断言测试。

---

## 5. 分期建议

| 阶段 | 内容 | 理由 |
|---|---|---|
| **P1 地基** | 平台自营身份 + `products.origin` + 新 ledger kind + `reconcile()` 扩展 + 测试 | 两者共同前提，改的是最底层，先做先暴露回归 |
| **P2 托管寄卖** | 寄卖单 + 受理队列 + 结算 + 前端 | 买家侧零改动，闭环最短 |
| **P3 教材集采回收** | 回收单 + 集采批次 + 成团/流团定时 + 前端 | 依赖 P1；回收与集采可再拆 |

**P1 单独可交付且用户不可见**，风险最低。建议至少先做 P1，把平台身份和账务扩展跑通、测试全绿，再往上叠业务。

---

## 6. 测试与验收

- Python：新增 `tests/test_consignment.py`、`tests/test_buyback.py`
  - 跑法沿用现有约定：系统 Python 3.8，`sys.path.insert(0, .../'Backend mission')`，`unittest discover -s tests`
- 冒烟：`workspace\smoke_consign.mjs`、`workspace\smoke_buyback.mjs`（参照 `smoke_want.mjs` 的写法）
- **必须有的断言**：
  1. 托管订单 `completed` 后，`reconcile()` 的 `held == 0` 且佣金金额正确
  2. 托管订单走退款时，佣金与寄卖结算不重复入账
  3. 集采预约人数超过 `stock_cap` 时不成团
  4. 非 staff 调用 `/api/consign/review` 返回 403
  5. 自营商品工单不能走 `outcome='resolved'`

---

## 7. 待你决策

1. **需求文档**：是否同意升到 v1.3，把这两个功能列为「模拟演练」范围？§2.3 目前是明确排除自营回收的，不先改文档，做完就是超范围实现。
2. **佣金率**：托管默认 10%（`commission_rate=1000`）是否合适？
3. **集采预约**：是否确认不收定金（纯登记，成团后自行下单）？
4. **节奏**：先做 P1 地基看效果，还是 P1+P2 一起交付？

---

## 附：与既有模块的对照

新功能刻意复用旧机制，避免再造一套：

| 新功能 | 复用的既有机制 |
|---|---|
| 托管商品被下单 | `checkout` / `order_action` / 订单状态机，**零改动** |
| 集采成团后下单 | `checkout`（卖家是平台商品） |
| 成团 / 流团定时 | `server.py` 现有 30 秒 `timer()` 线程 |
| 受理、驳回、结算留痕 | `audit` 表 + `staff()` 权限判断 |
| 商品分类与搜索 | `category` 直接沿用 books/living/sports/electronics |
