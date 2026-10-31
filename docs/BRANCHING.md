# 分支规范与里程碑

> **2026-10-29 分支整理**：远端长期分支收敛为 3 条（`main` + 2 条副分支）。
> 其余 14 条按「先归档、后删除」处理：先打 `archive/<原分支名>` 标签，再删分支，代码可随时恢复。

## 一、分支职责（2026-10-29 起）

| 分支 | 用途 | 当前提交 |
|---|---|---|
| `main` | 稳定/可发布；线上部署的唯一来源 | `f8b1019` |
| `release/2026-10-trial-hotfix` | 发布/回滚线；含 Vue + FastAPI 试验与 2026-10-25 回滚记录 | `c92567d` |
| `refactor/spec-v1-structure` | 重构线（通知/评价/交易拆分），4 个提交尚未并入 `main` | `c4bb27a` |

规则：

- 功能与修复分支从 `main` 切出，合并后即删，不再长期保留。
- `main` 不改写历史、不强制推送；合并前先核对目标分支和工作区是否干净。
- `master` 是整理前的 GitHub 默认分支，代码已归档为 `archive/master`；在仓库 Settings 把默认分支改成 `main` 后即可删除。

### 历史分支怎么找回

```bash
# 列出归档
git ls-remote --tags origin | grep archive/
# 从归档恢复成一条本地分支（例：恢复 master）
git branch master archive/master
```

## 二、功能里程碑（历史记录，截至 2026-10-20）

当时 `release/2026-10-trial` = `83eabc3`，比 `main` 领先 49 个提交。

| 功能 | 提交 | 里程碑 tag |
|---|---|---|
| 认证：会话持久化 + 注册校验 / 客户端 KDF 规范 | `523557e` `d5b11ba` | `milestone/2026-10-auth-session` |
| 好友系统：申请 / 同意 / 私聊门禁 | `199815f` | `milestone/2026-10-friends` |
| 校园论坛：分区 / 分页 / 求购联动 | `6e417ef` | `milestone/2026-10-forum` |
| 客服：会话移出聊天列表 + 门禁豁免 + 回复通知 | `7f87bfb` | `milestone/2026-10-support` |
| 管理端：档案只读会话 + 分级清除授权 | `bdcd9e0` | `milestone/2026-10-admin-dossier` |
| 商品详情：可读性重排 + 下单幂等 | `bb9408c` | `milestone/2026-10-product-detail` |
| 路由 / 事件聚合 + 顶部进度条 | `be88f4b` | `milestone/2026-10-router` |
| 文档 + 测试工具 | `7394ea6` `0e51ee6` | 含在 `v2026.10-trial` |
| 个人资料 / 头像改版 v1–v3 | `6219e90` `e648181` `7941fcc` `83eabc3` | `v2026.10-trial` |

### 当时的取舍

这些提交是**线性且互相依赖**的（好友依赖认证、论坛依赖路由、客服依赖好友门禁、管理端依赖客服会话）。
在任意中间点切出的「独立功能分支」缺少后续依赖，单独检出跑不起来；强行拆必须改写历史、重排提交，
风险大于收益。因此采用**里程碑 tag** 做不可变检查点。

## 三、日常工作流

```bash
# 1. 从 main 切功能分支
git switch main
git pull --ff-only
git switch -c feature/forum-pagination

# 2. 开发、自测、提交（一个提交只做一件事）
git add <具体文件>
git commit -m "feat(forum): 帖子分页改用 offset 游标"

# 3. 推送并开 PR（目标：main）
git push -u origin feature/forum-pagination

# 4. 合并后删除功能分支
git push origin --delete feature/forum-pagination
```

## 四、部署纪律

- 只从**干净、已打 tag** 的提交部署；部署前 `git status` 必须无未提交改动。
- 前端资源与 Worker 必须同一次 `wrangler deploy` 一起上传；只更其中一半会出现「页面旧、接口新」的错位。
- 当前线上版本以 `wrangler deployments status --name zhuanjiao` 为准，不把 Version ID 写死在文档里。
- 每次交付记录「本地提交 SHA → GitHub 远程 SHA → Cloudflare Version ID → 线上核验结果」。

## 五、待办

1. 在 GitHub Settings → Branches 把默认分支改为 `main`，然后删除 `master`（当前仍是默认分支，服务端拒绝删除）。
2. `refactor/spec-v1-structure` 的 4 个提交尚未并入 `main`，合并前需先解决 Python 版本注解与事务语义的回归。
3. 客服会话规则（是否「客服离线自动消失」）仍需产品确认，见 `docs/SUPPORT_CONTEXT-2026-10-20.md` 第六节。
