# 桌宠缩放修复 + 逛逛页 v3 改版（2026-11-04）

> 起点：`main` @ `422d902`。
> 回退点：分支 `backup/pre-home-v3-20261104`（= `422d902`）。
> 最终状态：**逛逛页是 v3 新版，桌宠三处修复一并保留**。

当天这条线来回走了三趟，先记清楚，免得以后对着历史犯迷糊：

| 时间 | 提交 | 状态 |
| --- | --- | --- |
| 10:18 | `b3c32fd` | 桌宠修复 + 逛逛页 v3 改版 |
| 10:40 | `9873901` | 用户判「好丑」，逛逛页退回 `422d902` 原样（桌宠修复保留） |
| 10:46 | 本文提交 | 用户要求「再改回去」，v3 恢复 |

三次都没有部署，线上一直是旧版。

---

## 一、桌宠「放大 / 缩小」的 bug（保留）

### 1.1 实测到的三个症状

用 Playwright 在 1440×900 下把外观滑杆从 100% 拖到 140% / 160% / 60%，量 `#ai-pet-body` 的包围盒：

| 档位 | 改前 | 改后 |
| --- | --- | --- |
| 100% | x=1338 w=82 → 右边界 1420（离屏幕 20px） | 不变 |
| 140% | w=114，x 仍是 1338 → 右边界 **1452，出屏 12px** | x=1322，右边界 1436（留 4px） |
| 160% | w=131 → 右边界 **1469，出屏 29px**（右半身被裁） | x=1305，右边界 1436（留 4px） |
| 60% | 位置不动，右下留 53px 空隙 | 以底边中点为锚点收拢 |

对话面板的「放大 → 还原」也有一次可见跳动：默认面板还原时从 `(1056,392)` 跳到 `(1056,360)`、高度 288 变 320；用户拖过尺寸时更明显，`(843,348) 585×541` 还原后跑到 `(843,139)`。

顺带发现两处同源问题：

- **气泡被压成竖排**。桌宠贴在屏幕右侧时，那句「早安，今天有要出的闲置吗？」会一字一行、并且溢出屏幕被裁。
- **首访提示和问候气泡叠在一起**，两条都读不清。

### 1.2 根因

1. 桌宠的 `left/top` 是左上角坐标。`applySkin()` 改完 `--pet-s`（尺寸）后没有重新夹回视口，所以放大时只会朝右下长，右边先出屏。
2. 气泡 `.ai-pet-reaction` 是 `.ai-pet` 的绝对定位子元素，而 `.ai-pet` 的宽度就是桌宠本身（82px）。绝对定位的**自动宽度按「到包含块右边还剩多少」算**，于是可用宽度只剩 41px —— 浏览器只能一字一行地折，再往外溢出。
3. `setPanelMax()` 只记住了尺寸，没记住位置；还原时 `placePanel()` 按桌宠重新贴一次，位置自然变了。

### 1.3 改法

| 位置 | 改动 |
| --- | --- |
| `ai-pet.js` `reanchor()` | 尺寸变化前后各量一次盒子，以**底边中点**为锚点重新贴位，再走 `moveTo()` 的夹取；同时 `savePos()` + `placePanel()` |
| `ai-pet.js` `fitFloating()` | 量气泡/提示条的布局宽度（`offsetWidth`，不受 transform 影响），算出水平补偿写进 `--bubble-dx` / `--hint-dx`，让它们整体平移回视口内；尖角跟着补偿量回指桌宠 |
| `ai-pet.css` | 气泡与提示条改 `width:max-content; max-width:min(200/260px, 100vw-32px)`，去掉 `white-space:nowrap`，位置改 `left: calc(50% + var(--…-dx))` |
| `ai-pet.js` `setPanelMax()` | 连 `left/top` 一起记；没拖过尺寸时记 0，还原交给 CSS 自然高度，不再被内容下限撑高 32px |
| `ai-pet.js` `mountPet()` | 首访时把问候延到提示条收起之后（7s），两条不再叠 |

### 1.4 验证

- 复测同上四个档位：右边界最大 1436（视口 1440），不再出屏；60% 收拢到 x=1346。
- 面板：默认 `(1056,392) 372×288` 放大再还原后完全一致；拖过尺寸的 `(843,348) 585×541` 也一致；窗口缩到 720×560 再放回 1440×900，尺寸与位置都能回原样。
- 气泡：100% / 160% / 390 宽下都是横排、完整可见；首次访问只出现提示条，7s 后才出问候。
- `node tests/frontend_modules.test.mjs`、`node --test tests/*.test.mjs tests/*.test.js` 全过。

---

## 二、逛逛页 v3 改版

v3 按当天的参考图重做：白底 + 墨绿 + 陶土橙，单通栏主视觉改双卡、频道磁贴改页签、商品卡去边框、版面顺序改为「主视觉 → 频道 → 转角发现 → 商品流 → CTA」。

- 用户第一次看到时判「好丑」，10:40 整体退回 `422d902`；
- 十分钟后要求「再改回去」，10:46 用 `git checkout b3c32fd --` 取回，与 `b3c32fd` 逐字节一致。

`index.html` 的缓存版本号：`home.css` 与 `main.js` 用 `?v=20261104-home-v3b`（这一次换 query 是为了把浏览器里缓存的 v2 挤掉），`ai-pet.css` 用 `?v=20261104-pet-fix`。`components/category-art.js` 重新删除，对应的 `modulepreload` 也去掉了。

### 2.1 来回切换的命令

```bash
# v3（当前）
git checkout b3c32fd -- "web 7M/home.css" "web 7M/src/pages/home.js" \
  "web 7M/src/components/home-hero.js" tests/home_browser_smoke.py
rm -f "web 7M/src/components/category-art.js"

# v2 / 422d902 原样
git checkout 422d902 -- "web 7M/home.css" "web 7M/src/pages/home.js" \
  "web 7M/src/components/home-hero.js" "web 7M/src/components/category-art.js" \
  tests/home_browser_smoke.py
```

切换后记得改 `index.html` 里 `home.css` / `main.js` 的 `?v=`，否则浏览器会拿缓存。

### 2.2 下次动首页视觉的顺序

这是本项目**第二次**首页改版当天回退（上次 `34e894b` → `8d35b08`，2026-11-02）。虽然这次十分钟后又恢复了，成本仍是三轮提交。下次按这个顺序走：

1. 先出 1–3 个**静态方案**（截图或可点 HTML），在聊天里让用户挑；
2. 用户选定后再改仓库代码；
3. 改完只做预览、不推 main，拿到一句明确的「可以」再提交推送。

---

## 三、部署记录（2026-11-04 11:13）

| 项 | 值 |
| --- | --- |
| 部署时间 | 2026-11-04T03:13:42Z（北京时间 11:13） |
| 代码版本 | `f2f366a`（工作树干净，`git status` 为空） |
| Version ID | `6f56228f-7890-4558-a78f-7a2d87dc4167` |
| 部署消息 | `home v3 f2f366a` |
| 上传 | 6 个静态文件（`index.html` / `home.css` / `home.js` / `home-hero.js` / `ai-pet.js` / `ai-pet.css`），191 个已存在跳过；Worker 14312.94 KiB，gzip 5104.73 KiB |
| Worker 启动 | 1046 ms |
| 线上地址 | https://zhuanjiao.wangzirui471.workers.dev |

部署前已跑 `wrangler deploy --dry-run`（215 个资源文件、294 个 Python 模块、D1/R2/KV/ASSETS 绑定齐全），并用 `whoami` 确认授权仍在（`wangzirui471@gmail.com`，account `824c84ca…`）。上一次线上是 2026-11-02 07:39Z 的 `home redesign restore 422d902`（`e5477a3b`），本次把它覆盖了。

### 上线验收（真实线上，不是本地）

| 项 | 结果 |
| --- | --- |
| `/api/health` | `{"ok": true, "trial": true}` |
| `/` 首页资源版本号 | `home.css?v=20261104-home-v3b`、`main.js?v=20261104-home-v3b`、`ai-pet.css?v=20261104-pet-fix` |
| `/home.css` 内容 | 含 36 处 `--ho-ink`（v3 令牌），确认不是旧版 |
| `/src/pages/home.js` | 含「转角发现」 |
| `/src/components/ai-pet.js` | 含 `reanchor`（桌宠修复已上线） |
| 浏览器（1440×950，走本机代理） | 24 张商品卡、1 个主视觉、7 个频道；`pageerror` 0 条；4xx/5xx 0 条 |

说明：`*.workers.dev` 在国内被 DNS 污染，本次验证全程走本机代理（`127.0.0.1:53414`），不代表校园网直连可用；正式对外仍需自有域名 + 备案。

### 回滚方式

```bash
cd "Backend mission"
node node_modules/wrangler/bin/wrangler.js rollback 6f56228f-7890-4558-a78f-7a2d87dc4167 --name zhuanjiao   # 先看历史
node node_modules/wrangler/bin/wrangler.js deployments list --name zhuanjiao                              # 找到要回的那一版
```

Cloudflare 控制台的 Deployments 页面也能一键回滚到 `e5477a3b`（= `422d902` 那版前端）。回滚只换 Worker/Assets 版本，不动 D1 数据。
