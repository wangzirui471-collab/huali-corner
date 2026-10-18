# Cloudflare 部署授权与实测状态

本文件记录**实测**结果，不记录预期。凡未实测的条目必须显式标注。

## 授权

已在项目所有者本人的 Windows 电脑上通过 Wrangler 浏览器 OAuth 完成授权。

```
wrangler whoami
  email     wangzirui471@gmail.com
  account   824c84ca5e382e2b4f8de6260d6b0017
  凭据      C:\Users\21203\AppData\Roaming\xdg.config\.wrangler\config\default.toml
```

授权只存在于这台电脑的该用户配置下。换机、换用户或凭据文件丢失后需要重新登录。

不把 Token、OAuth 凭据或密码写进仓库、聊天或文档。上面的路径只说明凭据位置，不含凭据内容。

## 已存在的资源（勿重复创建）

| 资源 | 名称 | 标识 | 区域 |
|---|---|---|---|
| D1 | `zhuanjiao-trial-db` | `530fa313-3285-42b9-aebd-e65e9b4e86ed` | APAC |
| R2 | `zhuanjiao-trial-images` | — | APAC / Standard |

代码绑定名：D1 → `DB`，R2 → `MEDIA`。

## 实测结果（2026-10-18）

环境：Windows，Wrangler 4.151.1，workers-py 1.17.8，Python Workers（Pyodide 3.14.2）。

远程绑定（`remote: true`）下 `wrangler dev` 通过 `/__preflight` 的结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| D1 `SELECT 1` | 通过 | 真实远程，冷启动 5570ms，热 380ms |
| R2 `HEAD` | 通过 | 真实远程，约 600ms |
| R2 写入/读回/删除 | 通过 | 专用诊断键，22 字节，已清理；桶仍为 0 objects |
| `hashlib.pbkdf2_hmac` | **不可用** | `AttributeError`；`hashlib.scrypt` 同样不可用 |
| Web Crypto PBKDF2 600000 轮 | 本地通过，**生产不可用** | 本地 workerd 正常；生产把迭代上限压在 100000，`NotSupportedError: iteration counts above 100000 are not supported (requested 600000)` |
| Pillow 图片处理 | 通过 | 12.2.0（12.3.0 无 wasm32 轮子）：JPEG/PNG/WebP 解码、EXIF 方向、去元数据、WebP 编码、坏图拒绝 |

D1 当前只有内部表 `_cf_KV`，**没有任何业务表**，原数据未迁移。（此条已被下文"数据迁移"覆盖）

## 新增异步适配层（已在真实运行时验证）

`Backend mission/app/cloudflare/` 下三个模块，只做运行时适配，不放业务规则：

| 模块 | 职责 |
|---|---|
| `d1.py` | 异步 D1 访问；`batch()` 是唯一事务原语；`expect()` 校验守卫是否命中 |
| `crypto.py` | 纯 Python PBKDF2-HMAC-SHA256（stdlib `hashlib`），600000 轮，输出格式与旧表完全兼容 |
| `media.py` | R2 私有对象；复用 `account/avatars.py` 的图片校验与重编码 |

在同一运行时、真实远程 D1/R2 上实测：

| 检查 | 结果 |
|---|---|
| `layer_d1` | 通过 —— `scalar` / 参数绑定 / **batch 原子性**（第 3 条语句失败后整批回滚，残留 0 行） |
| `layer_crypto` | 通过 —— 600000 轮、旧向量匹配、中文+emoji 往返、错误密码拒绝、salt 32 位 / digest 64 位 |
| `layer_media` | 通过 —— 重编码为 WebP、私有键布局、非图片拒绝、对象已清理 |

## 关键结论：现有后端不能直接迁移

同一运行时内实测：

- `threading.Thread.start()` 抛 `RuntimeError` —— **没有线程**
- `sqlite3` 可以 import，但那是无持久化的内存桩，不能当作数据库
- `socket` / `ssl` / `subprocess` 可 import，但无法真正工作
- `time.sleep(0.05)` 实际阻塞 68ms —— 会卡住单线程事件循环

因此 `ThreadingHTTPServer`、`core/database.py` 的 `_WRITE` 写锁、后台线程与 `BEGIN IMMEDIATE` 事务全部**无法运行**。迁移不是"换数据库地址"，而是请求层、数据访问层、认证加密三处都要改成异步。详见 [迁移设计](superpowers/specs/2026-10-17-cloudflare-trial-design.md)。

## 网络

- `index.pyodide.org`、`api.cloudflare.com`、`registry.npmjs.org` 均可达。
- 本机存在系统代理变量（`127.0.0.1:55879`），Wrangler 会提示并使用；当前可用，不需要关闭证书校验。
- 早期"被代理拦截"的阻塞已不再成立。

## 数据迁移（2026-10-18 完成）

来源：本机 `var-trial/market.sqlite3`（试用库）。导出前用 SQLite backup API 做了一致性快照，
因为该库当时正被另一个 dev server 写入。

| 项目 | 结果 |
|---|---|
| 表 | 29 张（含 `user_avatar_uploads`），索引 1 个 |
| 行 | 238 行，21 张表有数据 |
| 图片 | 27 个对象已进 R2，键为 `media/legacy/<user_id>/<upload_id>.webp` |

逐表行数与源库完全一致：audit 40、messages 29、uploads 27、sessions 62、members 12、
notifications 12、users 7、password_credentials 7、products 6、rooms 6、comments 4、
ledger 4、reactions 4、tickets 4、ticket_messages 4、nominations 3、offers 2、posts 2、
orders 1、settings 1、wants 1。

处理过的两个坑：

1. `core/database.py` 里的 `SQLITE_SCHEMA` 是旧版，缺 `users.last_login / degree_level /
   study_status / profile_version / avatar_upload_id`、`rooms.support / assignee / ticket_id`，
   也没有 `user_avatar_uploads` 表。这些是迁移脚本补出来的，必须以**本机实际结构**为准。
   `schema.sql` 已按真实结构重新生成。
2. `uploads.path` 存的是 Windows 绝对路径，云端无意义，已改写为 R2 键。

校验：在 Workers 运行时按 D1 的 27 条 `uploads` 记录逐个 HEAD R2 对象，27/27 命中；
抽查对象 SHA-256 与表内 `digest` 完全一致。`wrangler r2 bucket info` 的 `object_count`
统计滞后，不能作为判断依据。

未迁移：`var/`（演示库，39 行）未导入，避免与试用数据混用。本机 `var-trial/uploads/`
另有 30 个无人引用的孤儿文件，未上传。

**注意：远程 D1 已可被多人写入。** 迁移后出现了非本机来源的账号
（`13900000001 / 测试同学`，含密码凭证与 2 个会话），说明已有其他入口在写这个库。

## 密码派生：三个方案的生产实测（2026-10-18）

要求是保住 PBKDF2-HMAC-SHA256、600000 轮、与旧表 `password_credentials` 完全兼容。
三个方案全部在**生产环境**（非本地 workerd）实测过：

| 方案 | 本地 | 生产 | 结论 |
|---|---|---|---|
| `hashlib.pbkdf2_hmac` | — | — | Pyodide 运行时就没有这个函数 |
| Web Crypto `crypto.subtle.deriveBits` | 通过 | **失败** | 迭代上限 100000，600000 直接 `NotSupportedError` |
| wasm 版 pycryptodome | 通过（385ms，结果正确） | **失败** | 整包在 Workers 内存里加载不起来，所有路由 1105 |
| 纯 Python（stdlib `hashlib.sha256`） | 通过 | **结果正确，但 CPU 超限** | 见下 |

最终采用纯 Python 实现（`app/cloudflare/crypto.py`）：预计算 HMAC 的 ipad/opad
中间状态、整数异或累加，比 `hmac.new` 写法快约 4 倍。正确性已在两个层面验证：

- 本机 CPython：600000 轮产出旧参考向量 `af9dd8ed…07adc6b`，与 `hashlib.pbkdf2_hmac` 一致；
- 生产环境：1000 / 10000 轮的摘要头与独立 Node 参考值逐字符一致（`ff1173dd…` / `51c3c167…`）。

### 阻塞：免费计划 CPU 上限

生产环境发起注册（600000 轮）约 8.4s 后被 Cloudflare 以 **503 / error 1102**
（Worker exceeded CPU time limit）终止。免费计划 CPU 预算是 10ms，而本机 CPython
跑完 600000 轮需要约 657ms，Workers（Pyodide）会更慢——这不是代码可以优化的差距。

结论：**注册、登录、恢复码验证都需要 Workers 付费计划**（CPU 上限 30s，$5/月起）。
升级后现有代码无需改动即可工作；不要为了省 CPU 降低轮数或换算法。

实测时的失败请求在 KDF 阶段就被终止，D1 无残留数据（users 总数仍为迁移后的 10，
无 `13800001111` 测试行、无 auth_attempts 残留）。

## 生产部署（2026-10-18）

站点：https://zhuanjiao.wangzirui471.workers.dev （版本 `208ade13…`）

| 路由 | 状态 |
|---|---|
| `GET /api/config` | 200 —— 校区、楼栋、学院配置与旧实现同形 |
| `GET /api/products` | 200 —— 真实 D1 数据（分页/搜索/收藏/点赞/卖家信任标记） |
| `GET /api/product?id=` | 200 |
| `POST /api/auth/register` | 代码就绪，**需付费计划**（见上） |
| `POST /api/auth/login` | 代码就绪，**需付费计划**（见上） |
| `POST /api/auth/logout`、`GET /api/me` | 依赖会话，随登录一并可用 |
| `GET /media/<id>` | 200 —— R2 私有对象读取，权限规则与原实现一致 |
| 其余 `/api/*` | 501 显式标注"该接口尚未在试用版开放"，不静默返回空数据 |

静态资源由 Workers Assets 托管，`run_worker_first` 保证 `/api` 与 `/media` 先进 Python。

## 未完成

- ~~业务表未初始化，原数据未迁移~~（已完成，见上）
- ~~后端异步改造未完成~~（首批接口已上线）
- ~~完整站点未部署~~（已上线，读路径可用）
- **注册/登录待 Workers 付费计划解锁**（代码已就绪并验证，唯一阻塞是 CPU 预算）
- 定时触发未配置
- 剩余业务域未移植（发布、订单、聊天、客服、管理端等，前端共引用约 70 个 `/api/*` 端点）
