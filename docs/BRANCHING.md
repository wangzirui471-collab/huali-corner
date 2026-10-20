# 分支规范与里程碑（2026-10-20）

> 背景：原来的 `fix/f01-banned-seller-release` 已经装了 49 个提交（认证、好友、论坛、客服、管理端、商品详情、路由、个人资料…），
> 早已超出 F-01 的范围。本文档把分支职责、功能里程碑和后续规则固定下来，避免再出现「一个分支装所有东西」的情况。

## 一、分支职责

| 分支 | 用途 | 规则 |
|---|---|---|
| `main` | 稳定/可发布 | 只接受来自 `release/*` 的合并；不直接提交 |
| `release/2026-10-trial` | 2026-10 校园试用的集成分支 | 当前生产发布分支；功能合并到这里，验证后再进 `main` |
| `feature/<模块>-<简短描述>` | 新功能 | 从 `release/2026-10-trial` 切出，PR 回合 |
| `fix/<模块>-<简短描述>` | 缺陷修复 | 同上；不要再用 `fix/f01-*` 这种编号名装整批迭代 |

历史遗留的 `origin/fix/f01-banned-seller-release` 已被 `release/2026-10-trial` 完全包含，保留作为回滚备份；
`main` 合并完成后可删除：

```bash
git push origin --delete fix/f01-banned-seller-release
```

## 二、功能里程碑

当前 `release/2026-10-trial` = `83eabc3`，比 `main` 领先 **49 个提交**，落后 0 个。

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

发布点：**`v2026.10-trial`**（annotated tag，指向 `83eabc3`）。

### 为什么没有把 49 个提交拆成多个独立分支

这些提交是**线性且互相依赖**的（好友依赖认证、论坛依赖路由、客服依赖好友门禁、管理端依赖客服会话）。
在任意中间点切出的「独立功能分支」缺少后续依赖，单独检出跑不起来；强行拆必须改写历史、重排提交，
风险远大于收益。因此采用**里程碑 tag** 做不可变检查点：既能按功能追溯/回滚，又不动历史。

## 三、日常工作流

```bash
# 1. 从发布分支切功能分支
git switch release/2026-10-trial
git pull --ff-only
git switch -c feature/forum-pagination

# 2. 开发、自测、提交（一个提交只做一件事）
git add <具体文件>
git commit -m "feat(forum): 帖子分页改用 offset 游标"

# 3. 推送并开 PR（目标：release/2026-10-trial）
git push -u origin feature/forum-pagination

# 4. 发布分支验证通过后，再合并 main 并打 tag
```

## 四、部署纪律

- 只从**干净、已打 tag** 的提交部署；部署前 `git status` 必须无未提交改动。
- 每次部署把 Cloudflare 的 Version ID 记进发布说明（`wrangler deployments list` 可查）。
- 截至 2026-10-20 13:30，线上最新版本为 `97816388-d5e6-4bb1-9dd9-2141333ac66f`
  （11:52 部署），比 `docs/SUPPORT_CONTEXT-2026-10-20.md` 记录的 `91e8bc37` 更新。
- 前端资源与 Worker 必须同一次 `wrangler deploy` 一起上传；只更其中一半会出现「页面旧、接口新」的错位。

## 五、待办

1. `main` 尚未合并这 49 个提交；合并前建议先在试用环境完整回归一轮（登录/发布/下单/客服/论坛/后台）。
2. 合并完成后删除 `fix/f01-banned-seller-release` 远程分支。
3. 客服会话规则（是否「客服离线自动消失」）仍需产品确认，见 `docs/SUPPORT_CONTEXT-2026-10-20.md` 第六节。
