# 转角 · 计算机工程学院试点

一个已经连接真实 SQLite 数据库的本地模拟交易原型，包含手机/电脑网站、原生微信小程序源码、社区聊天及客服后台。不是公开运营版本；未接真实短信、身份核验、微信收款或学校系统。

**本轮分层升级**：商品编辑、下架恢复、组合筛选与分页已接入；保留私密草稿、独立客服、退货重售、信誉和通知。详见 [本轮交付与升级说明](docs/LAYERED_COMPLETION.md)。源码包可用 `python scripts/build_trial_package.py --output /tmp/zhuanjiao-trial.zip` 生成，包含完整后端包、ES模块树及小程序，不带运行数据。

**计算机工程学院可登录试用版**：在当前功能分支选择 **Code → Download ZIP** 下载全部源码，或使用本轮交付的分层试用ZIP；解压后双击 `start-trial.bat`，或运行 `python "Backend mission/server.py" --trial`。同学使用手机号＋密码独立注册，不发送短信、号码未验证；支持发布、收藏、聊天与模拟交易。独立的 `var-trial/` 保留账号和图片，关闭共享测试验证码与客服快捷登录。管理员由运营者单独创建。见[试用与后端部署说明](docs/TRIAL.md)；仍需真实部署后才有同学可访问的公网网址。

要发链接给同学看效果，可使用独立的[公开演示版部署说明](docs/PUBLIC_DEMO.md)。先运行 `python scripts/build_public_demo.py --output dist/public-demo` 导出，再把该目录上传静态托管平台；静态演示不需要让自己的电脑持续运行。该包只展示虚构数据，未提供真实注册、地址填写、交易或后台入口。公网网址需要在托管平台实际部署后生成。

## 目录结构

2026-10-15 整理后的布局：前后端分家。

```
huali-corner-trial/
├── Backend mission/     后端：入口 + 业务模块 + 部署配置
│   ├── server.py      HTTP 服务与路由
│   ├── app/           业务模块（分层，见下）
│   │   ├── market.py  Market 组合类：把下面各模块拼成一个对象
│   │   ├── core/      config(路径) database(Store) errors(异常与校验)
│   │   └── account/ catalog/ trade/ community/ support/ notifications/ ops/
│   │   └── seed.py    演示数据播种（在app包内）
│   └── manage_trial.py render.yaml requirements.txt
├── web 7M/              前端：网页静态文件 + 小程序
│   ├── index.html market.css styles.css public-demo.js
│   ├── src/           ES 模块（入口 main.js，分层，见下）
│   │   ├── core/      dom format state http nav shell asset
│   │   ├── components/ forms category-art product-card
│   │   ├── pages/     home product publish cart orders listings
│   │   │              me community messages support
│   │   ├── auth/      login
│   │   ├── actions/   index(分发) ui catalog trade social support account change
│   │   └── router.js  路由表与 render
│   ├── assets/        图片、Logo、演示素材
│   └── miniprogram/   微信小程序
├── docs/                TRIAL.md、ASSET-CREDITS.md、research/
├── var/                 演示模式数据
├── var-trial/           学院试用数据（真实账号与上传图片，勿删）
└── start-trial.bat / start-trial-8081.bat   启动脚本
```

路径全部由 `Backend mission/app/core/config.py` 推导：它先看上一级有没有 `web 7M`，
有就把根目录定为上一级（正常项目结构）；没有就退回自身目录
（后端被单独拷出去部署时走这个分支）。

## 启动网站

Python 3.12+。当前云环境已安装 Pillow；新机器需先安装依赖：

```bash
cd "/workspace/campus-market/Backend mission"
python3 -m pip install -r requirements.txt
python3 server.py --port 8080
```

本地浏览器访问 `http://127.0.0.1:8080`。仅绑定回环地址；不要把此演示服务直接暴露公网。页面是可运行软件，并非静态效果图。默认生成13件明确标为演示的商品和2条演示帖子；`--no-seed` 可禁用示例商品。

数据默认在 `var/`，可指定 `--data /path/to/private-data`。重新启动会保留数据，不会覆盖已发布商品。不需要修改原来的点云网站仓库 `/workspace/-`。

### Windows 启动与旧版本更新

在 PowerShell 中先进入解压后的项目目录，逐行运行（路径按实际位置调整）：

```powershell
cd "E:\zi\huali-corner-trial\Backend mission"
python -m pip install -r requirements.txt
python server.py
```

保持终端开启，在本机浏览器访问 `http://127.0.0.1:8080`。命令是 `python`，前面没有点号。PowerShell 的个人配置脚本被执行策略阻止，与 Python 网站启动是不同问题，不需要为此放宽执行策略。

更新分层版本时，不要只替换 `server.py`。先停止服务并备份原数据，再在新目录完整解压全部源码，用 `--data` 指向原试用数据目录。升级只增量迁移数据库；网页 `src/` 和后端 `app/` 必须成套更新。原 `var-trial/`、照片和备份不能删除或用演示数据覆盖。先在副本中核对订单和账务，再用于原数据。推荐Python 3.12；本轮没有Windows实机验证。

若 pip 报 `Cannot connect to proxy`，应先检查本机代理及 pip 代理配置；连接失败后的 `No matching distribution` 不能单独证明依赖版本不存在。不要通过禁用 TLS 校验来解决代理问题。

## 测试登录

登录弹窗提供卖家、买家、客服三个快捷体验账号。也可以填写合法格式手机号并获取页面显示的本地测试验证码。**没有短信发出，任何人知道测试号码均可模拟登录，绝不可用于公开运营。** 本地验证码5分钟有效、一次使用、错误次数受限。

- 卖家：`13800000001`
- 买家：`13800000002`
- 客服/平台管理员：`13800000003`

以上仅供本地演示，不发送短信、不收集身份证或学生证明。手机号只代表账号登录条件，不显示学生或实名认证标识。公开试运营必须先替换短信实现并移除开发账号登录。

## 已实现流程

- 二手书、宿舍、运动与电子产品闲置；逐本发布，版次、ISBN、出版社、笔记/缺页/附件选项。
- 正面、侧面、顶部三张不同实拍图校验，可补充版权页和内页；不保证自动识别网图或盗版。
- 商品详情、公开卖家主页、组合筛选、稳定翻页、收藏、点赞、链接分享和规则参考估价。支持学院、专业、课程、版次、成色、交付方式和价格；按所选交付总价筛选。
- 三步发布、私密草稿自动保存、冲突提示与恢复；在售/主动下架商品可编辑，旧报价随关键修改失效，已生成订单保留原快照。
- 主动下架可恢复；售后移除须确认实物和退款后从重售草稿发布，违规和不明确的历史移除不能绕过。
- 同卖家多件加入取货清单，合并下单。送货费按所选商品的最高送货费收取一次，商品总价与送货费分别显示。
- 自提/卖家送货、地点与时间快照、卖家确认时段、结构化改约（另一方接受才生效）。付款前30分钟超时关闭；已付款但下单24小时后卖家仍未确认时段则自动模拟退款取消。
- 模拟付款、交接、确认收货；买家核对交接后24小时自动收货，售后处理中暂停。卖家单方面点已交付不会开始自动结算。
- 支付、结算、退款、结算冲回独立流水；客服可查询资金平衡。所有金额为模拟，不产生真实资金。
- 订单售后/举报/信誉申诉，双方可补充说明，客服认领、内部备注、处理理由和复核。当前支持模拟全额退款与API部分退款；退货实际验收需人工核实记录，未实现自动物流退货。
- 信誉初始100，低于60无法发布；举报不自动扣分，管理员必须关联已核实工单、说明理由，同工单不重复扣分；用户可查看原因和申诉。
- 平台工作人员不能处理自己发起或参与的订单/商品投诉和对应信誉处罚。
- 私聊、拉黑、帖子/评论、主动加入学院群和总群；学院群满500人自动分流，注册不自动加群。
- 自愿申请群管理员，平台审核授权；群管理与客服/资金权限分离。群禁言与移除消息有服务端接口，精细群成员管理界面待后续打磨。
- 客服工作台08:00—20:00服务文案、工单队列、审核、审计、备份和对账。页面上的服务时段不是保证真人在线；人员由运营者安排。

## 微信小程序

用微信开发者工具导入 `web 7M/miniprogram/`；填写自己的 AppID，`touristappid` 仅作开发配置。`app.js` 的 `globalData.baseURL` 默认指向本地后端。

代码包含首页、商品详情/收藏分享、三图发布、手机号测试登录、清单合并订单、订单交付与售后、个人资料、社区及私聊群聊、客服工单。

本地开发者工具请求回环地址可能需在**工具本地测试设置**允许非合法域名请求；这不代表上线可绕过HTTPS/合法域名和审核要求。真机无法访问电脑自己的回环地址。本次没有微信开发者工具、真实AppID或审核环境，因此只验证JavaScript语法、部分客户端逻辑与共用后端接口，**未声称微信编译、真机或发布通过**。

小程序展示基础核心流程，客服高级信誉调整、资金对账和备份主要在电脑网页工作台操作。

## 验证

```bash
python3 -m unittest discover -s tests -v
node tests/native_client.test.js
node tests/native_catalog.test.js
node tests/native_order.test.js
node tests/frontend_modules.test.mjs   # 前端 ES 模块：可加载性 + 依赖无环
python3 tests/layered_browser_smoke.py
python3 tests/public_demo_smoke.py
python3 tests/ui_redesign_smoke.py
```

浏览器验证需安装 Python Playwright 和 Chromium。当前环境已有，脚本使用 `/usr/bin/chromium`；新机器请自行按官方方式安装，勿禁用包签名或TLS验证。脚本用临时数据库和自建测试图，不污染实际数据。

新版截图在 `artifacts/redesign-desktop.png`、`artifacts/redesign-mobile.png` 和 `artifacts/redesign-small-mobile.png`。

2026-10-15界面改版：参考用户提供的闲鱼/转转的信息层次，改为顶置搜索、频道分类、快捷入口、校园专题与大图商品列表，使用明亮黄色强调色。网页和小程序源码样式同步调整。`web/assets/market-demo-photos.png` 是原创AI生成的4×4示意图素材，仅用于明确标为演示的种子商品，通过界面裁切展示，不代表实物照片或版次核验。真实商品仍展示用户上传的照片，且不使用这份示意图。

## 数据备份、恢复与运维

客服工作台「保存完整备份」生成 `var/backups/market-*.zip`，包含SQLite一致性快照、上传图片与清单。启动后的后台任务每30秒处理订单超时，每24小时至少创建一次备份（服务停止时不会执行）。初版不自动删除旧备份，应监测磁盘并另存副本。

恢复前停止服务，将备份解压到**新的空数据目录**，保留 `market.sqlite3` 和 `uploads/`。使用 `--data 新目录` 启动；启动会按新目录重绑定图片路径。先核对订单、图片及对账，不覆盖现有数据。应定期演练恢复；备份中包含私人数据，不可公开下载。

单实例SQLite用于本地与小规模封闭试用，不承诺高并发生产能力。真实开放前需要正规的认证、支付方案、HTTPS部署、监控、隐私/交易规则、反滥用和负载验证。

## 学校目录与隐私

学校目录草稿仅提取用户文件中的校区、学院、专业、层次，不导入学生姓名、学号、成绩或班级。补考文件不能证明全部院系，新旧学院名称仍待核实。试点使用源文件中的「计算机工程学院」，个人可以不填学校信息。

原始学生XLSX位于平台附件区域，不在项目、部署包或公开静态文件内。`docs/research/` 只含去重的组织目录，非个人名单。官网与支付官网访问曾被网络代理403阻断，最新学校数量和费率没有获得核实。

## 预算与限制

未购买外部服务。3000元作为试做预算；本项目没有实际交易手续费。后续服务器/短信/小程序、AI工具和人工费用需另行安排，不承诺所有服务都可由个人主体申请。

4元仅为书籍建议起价，不强制抬价，允许免费转让。当前无平台先行赔付、无无条件退款保证；站外交易不具备站内退款能力，但可接受举报。真实法律责任不能用「仅提供平台」一概排除。
