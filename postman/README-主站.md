# 转角主站 · 全接口自动化（8081 / 试用模式）

针对 `Backend mission/server.py` 里 `handle_request` 的**全部 `/api/*` 路由**：99 个路由全覆盖，
展开成 **130 个请求 / 388 条断言**。本地实测 **388/388 通过，16.8 秒跑完**。

```
postman/
├── 转角主站-全接口.postman_collection.json   # 主集合（10 组，130 请求）
└── tools/
    ├── gen_all_apis.py                      # 生成器：路由表改成新接口后重新生成集合
    └── png_{front,side,top}.b64             # 发布商品要用的三张测试图
```

## 1. 跑起来

### 1.1 起一个**隔离数据目录**的实例（别用真实数据）

```powershell
cd "E:\zi\huali-corner-trial\Backend mission"
$env:HUALI_DATA_DIR="E:\zi\huali-corner-trial\_pm-test"     # 随便一个空目录
.\..\.venv-trial\Scripts\python.exe server.py --trial --port 8081 --no-seed
```

启动时会打印一个**管理员手机号和初始密码**（也写在 `_pm-test\admin-initial-password.txt`），后面要用。

### 1.2 填两个变量

集合变量里填：

| 变量 | 说明 |
| --- | --- |
| `adminPhone` / `adminPassword` | 上一步自动创建的管理员账号。**填了它，80 组的客服/管理端用例才真正跑通**；留空时那些用例按「401/403 被拒」断言（等于顺带把权限基线也验了） |
| `baseUrl` | 默认 `http://127.0.0.1:8081` |

卖家 / 买家账号不用管：集合的前置脚本每轮会随机生成 139 开头的手机号，跑完即弃。

### 1.3 运行

```powershell
cd "E:\zi\huali-corner-trial\postman"
newman run "转角主站-全接口.postman_collection.json" `
  --env-var baseUrl=http://127.0.0.1:8081 `
  --env-var adminPhone=<管理员手机号> --env-var adminPassword=<初始密码>
```

Postman 里则是：导入 → 选环境 → 集合右键 **Run collection**。

## 2. 集合怎么组织的

| 分组 | 内容 |
| --- | --- |
| 00 准备 | 建号 → 传三张图 → 发布 → 下架/上架 → 读图 → 买家下单付款。**后面所有用例都依赖这里产出的 id** |
| 10 账号与认证 | 注册/登录/改密/找回/注销/退出/发码，含「旧密码错→被拒」「注销后 token 失效」 |
| 20 个人资料 | 资料读写、头像上传+确认、徽章、通知、公开主页、客服档案 |
| 30 商品 | 列表、详情、我的、收藏点赞、状态、估价/描述助手、求购 |
| 40 交易 | 下单、付款、发货、交接、收货、改约、评价、报价、资金对账 |
| 50 工单与售后 | 工单创建/回复/结案/关联订单、信誉扣分（dry_run）、AI 设置 |
| 60 社区与聊天 | 群、私聊、消息收发/撤回/回执/隐藏、好友、帖子评论、举报 |
| 70 客服会话 | 客服会话列表/建会话/认领/关闭 |
| 80 管理与审计 | 审计、客服账号、敏感词、封禁、清号、备份、只读聊天 |
| 90 收尾 | 下架测试商品、退出登录 |

三条通用规则写在每个请求的测试脚本里：**状态码在预期集合内**、**响应 < 5s**、
**4xx 必须有 `error` 字段 / 2xx 不能带 `error`**。列表类接口直接返回数组，断言已兼容。

## 3. 踩过的坑（都已写进集合）

| 坑 | 表现 | 处理 |
| --- | --- | --- |
| 年级要带「级」 | 注册一直 400「请选择正确的年级」 | 用 `2024级`；合法值见 `/api/config` 的 `grades` |
| 下单必须带 `appointment` | `checkout` 400 | 前置脚本自动算「两小时后」的秒级时间戳 |
| 资料接口要带整型 `profile_version` | 改资料 400 | 从 `/api/me` 取出来再回填 |
| 商品已下单就下架不了 | `product/status delist` 400 | 下架/上架放在**下单之前** |
| 求购字段是 `keyword` 不是 `title` | 400 | 已按 `create_want` 的真实签名写 |
| 帖子分区白名单 | 422 | 只能是 交流/求购/毕业季/互助/交换人生/代拿快递 |
| AI 助手依赖 8093 | `/api/ai/chat`、`/api/ai/price` 等返回 **503** | 先起 `ai_service/server.py`；没起则是 503（是「服务未启动」，用例已接受） |
| 未发布的图片 | `/media/xxx` 403 | 读图用例放在发布之后 |
| 试用模式 | `/api/auth/code` 403 | 试用模式不发验证码 |
| 平台视角接口 | `/api/product/removed` 403 | 需要客服/管理员 token |

## 4. 加了新接口怎么办

改 `postman/tools/gen_all_apis.py` 里的 `ITEMS` 表（一行 = 一个请求：分组、名称、方法、路径、
query、body、预期状态码、用哪个 token、要提取哪些变量），然后：

```powershell
cd "E:\zi\huali-corner-trial\postman\tools"
python gen_all_apis.py
```

它会重新生成上一层的 `转角主站-全接口.postman_collection.json`，跑一轮 newman 校准预期状态码即可。

## 5. 边界说明

- 有 7 个「必须靠已有 id 才成立」的接口（报价应答、改约应答、好友申请处理等）用 `id=0` 试探，
  断言只要求 **400/403/404 而不是 500**，用来保证「不存在的资源不会打挂服务」。
- `80 · 管理与审计` 组里的高危操作（封禁、清号、重置密码）都只作用在**本轮随机注册的测试账号**上，
  且需要管理员 token；不填 token 时全部按 401/403 通过。
- 集合**会写数据**（注册、发布、下单、发帖）。所以必须配合 `HUALI_DATA_DIR` 的临时目录使用。

## 6. 放到 GitHub Actions 上自动跑

已经写好了：`.github/workflows/postman-api-tests.yml`。
push 到 `main/master/develop/feature/**`、开 PR、或手动 `workflow_dispatch` 都会触发。

它在干净的 Linux 容器里做四件事：
装依赖 → 起 AI 服务（8093，`HC_AI_MOCK=1`，先 `ingest.py` 现造索引）→
起后端（8081，`--trial --no-seed` + 临时数据目录）→ 两个都探活通过后才跑 Newman。

几个要点：

- **数据隔离**：后端数据目录指向 `/tmp/huali-ci-data`，跑完即弃，不碰仓库里的 `var-trial/`。
- **管理员凭据**：用 `HUALI_ADMIN_PHONE` / `HUALI_ADMIN_PASSWORD` 显式指定，
  所以不用去解析 `admin-initial-password.txt`，密码也不会落进仓库。
  想更讲究就在仓库 Settings → Secrets 里建同名的两个 Secret，工作流会优先用它们。
- **AI 服务必须先起**：不然 5 个 `/api/ai/*` 会拿到 503。
  走 `HC_AI_MOCK=1` 时不联网、不要 API Key，所以这个门禁**不需要配任何 Secret 就能跑**。
- **AI 集合那个 job 目前是 `continue-on-error`**：因为 `ai_service/server.py` 里
  `rag.SOCIAL_REPLIES` 那个多轮对话的 bug 还在，「06 多轮对话」必红。
  修掉之后把那行删掉，它就变成真正的门禁了。
- 报告会作为 artifact 上传（junit xml + 日志），失败时会把后端和 AI 服务的日志 tail 出来。

## 7. 本地一键跑（不想等 CI 的时候）

双击 `postman\一键跑测试.bat`，或者在命令行里：

```powershell
# Windows 建议用项目虚拟环境，里面有 Pillow（后端处理头像要用，系统 python 常常没装）
"E:\zi\huali-corner-trial\.venv-trial\Scripts\python.exe" postman\run_all.py
```

它会自动：起 AI 服务（8094）+ 后端（8095，临时数据目录）→ 探活 → 依次跑三套集合 →
生成 `postman\运行报告.md` → **关掉刚才起的两个服务**。全程大约 30 秒。

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--keep` | 跑完不关服务，留着手动调（会打印端口给你） |
| `--only api` | 只跑某一套，可选 `api` / `ai` / `faq`，能写多个 |
| `--api-port N` / `--ai-port N` | 换端口，默认 8095 / 8094（刻意避开你平时用的 8081 / 8093） |
| `--newman "命令"` | newman 找不到时手动指定；默认 PATH → WorkBuddy 自带那份 → npx |

退出码：**全绿 0，有失败 1，服务没起来 2**，所以挂到任何 CI 上都能直接用。
跑完会保留 junit 原始 xml 在系统临时目录里（日志末尾会打印路径）。

> 那个 `.bat` 里的注释刻意写成英文：cmd.exe 解析批处理时按字节读，
> 中文和 `^` 续行符挨在一起会把命令行截断（实测直接崩成一堆乱码），
> 所以真正的逻辑都放在旁边的 `run_all.py` 里，`.bat` 只负责调用它。

## 8. 在 Postman 界面里跑（不是在命令行）

之前集合只写成了 `postman/*.postman_collection.json`，那是 **Newman 用的 2.1 格式**，
Postman 12 的「打开文件夹」（Local View）**不认**——它只扫
`postman/collections/<集合名>/` 下「一个请求一个 `*.request.yaml`」的目录树（Collection Schema 3.0）。
所以在软件左侧根本看不到它们（之前只有一个空的「转角后端API」）。

现在两份同时存在，由 `tools/to_postman_files.py` 从 json 生成 yaml：

| 格式 | 位置 | 给谁用 |
| --- | --- | --- |
| 2.1 单文件 | `postman/转角主站-全接口.postman_collection.json` | Newman / GitHub Actions |
| 3.0 目录树 | `postman/collections/转角主站-全接口/*.request.yaml` | Postman 界面 |

**在界面里跑的步骤：**

1. 切回 Postman 窗口，左侧应出现三套集合（它监听文件变化）；
   没出现就 `File → Open Folder` 重新选一次 `huali-corner-trial`。
2. 右上角环境选择器选「**转角**」（`baseUrl` 已填 `http://127.0.0.1:8081`）。
3. 在集合上点 **Run** → Run，跑整条链路（130 个请求按 order 顺序执行）。
4. **不要只点单个请求的 Send**——token 是「00 · 准备」里登录请求写进集合变量的，
   单独发一个必 401。

**两条常见报错，其实是同一件事：**

| 现象 | 原因 |
| --- | --- |
| `401` + `{"error":"请先登录"}` | 路径写错了。`/api/user/login` **不存在**，正确的是 `/api/auth/login`。未知路径会被兜底鉴权当成「未登录」返回 401，所以看起来像密码错误 |
| `Cannot read properties of undefined (reading 'token')` | 上一步 401 了，响应体里只有 `error` 没有 `token`，脚本却按成功去取 → TypeError |

**改动怎么同步（很重要）：**

- 接口变了 → 改 `tools/gen_all_apis.py` 的 ITEMS → 跑 `gen_all_apis.py` → 跑 `to_postman_files.py`
- **不要手改 `collections/` 下的 yaml**：转换时整个目录会重建，手改会被覆盖
- 反过来，在 Postman 界面里改的请求也只会写进 yaml，json 不会跟着变，Newman 跑的还是旧的——
  所以把 `gen_all_apis.py` 当成唯一源头
