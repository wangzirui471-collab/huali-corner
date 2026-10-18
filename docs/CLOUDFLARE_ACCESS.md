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
| Web Crypto PBKDF2 600000 轮 | 通过 | ASCII 与中文/emoji 两个向量均匹配独立 Node 参考值 |
| Pillow 图片处理 | 通过 | 12.2.0：JPEG/PNG/WebP 解码、EXIF 方向、去元数据、WebP 编码、坏图拒绝 |

D1 当前只有内部表 `_cf_KV`，**没有任何业务表**，原数据未迁移。

## 新增异步适配层（已在真实运行时验证）

`Backend mission/app/cloudflare/` 下三个模块，只做运行时适配，不放业务规则：

| 模块 | 职责 |
|---|---|
| `d1.py` | 异步 D1 访问；`batch()` 是唯一事务原语；`expect()` 校验守卫是否命中 |
| `crypto.py` | 异步 PBKDF2-HMAC-SHA256，600000 轮，输出格式与旧表完全兼容 |
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

## 未完成

- 业务表未初始化，原数据未迁移
- 后端异步改造未完成
- 完整站点未部署，**没有公网地址**
- 定时触发未配置
