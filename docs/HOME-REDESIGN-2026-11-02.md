# 逛逛页视觉重构（2026-11-02）

> 范围：**只改逛逛（首页）**。社区、论坛、商品详情、订单、后台等页面未改结构与交互；
> 唯一跨页改动是 `core/shell.js` 里给首页追加了一段导航行提示（`active==='home'` 才渲染）。
> 回退点：`backup/pre-home-redesign-20261102`（= `8113c92`，重构前最后一版，已推到 GitHub）。

---

## 1. 为什么改

用户给了一张参考图，要求四件事：

1. 按图重构首页，**保留所有功能**，颜色不要单一；
2. 首页很多按键点了都落到同一个页面，要改掉；
3. 不要「小转推荐」；
4. 只动逛逛，其他页面不要动。

旧版的问题正好对上第 2 条：频道行 6 个按钮、专题轮播 3 张卡，全部走
`go('home')` ——筛选值变了，地址没变，页面标题也一直是「猜你喜欢」，
用户看到的就是「点什么都在同一页」。第 3 条对应首页那条 `rec-rail` 横滑推荐轨。

## 2. 结构对比

| 区块 | 旧版 | 现在 |
| --- | --- | --- |
| 频道行 | 6 个（推荐/二手书/宿舍生活/运动好物/电子产品/免费送），全部 `go('home')` | 7 个彩色磁贴，**六个商品频道各有地址段**（`#home/books`、`#home/free`…），第七个「校园求购」直达 `#forum/wants` |
| 主视觉 | 1 张通栏轮播，3 张 slide 只带「分类+关键词」，点开仍是同一页 | 2 张并排卡（教材 / 宿舍好物），各 3 张 slide，**每张 slide 自带去处**（频道页 / 发布页 / 求购页） |
| 推荐轨 | 「小转 · 为你推荐」横滑轨 + 换一批 | **删除**（组件 `rec-rail.js`、CSS、`rec-refresh` 动作、`/products?rec=1` 请求一并移除） |
| 商品流 | 标题固定「猜你喜欢」 | 随频道变：教材书籍 / 宿舍生活 / 电子产品 / 运动好物 / 免费好物 / 收藏好物；带「← 全部好物 / 当前频道」面包屑 |
| 底部 | 无 | 「让闲置，遇见下一位主人」CTA + 发布闲置（与参考图一致） |
| 头部 | 品牌黄、校区按钮在首行 | 品牌黄 + 紫色小转 AI、搜索框黄色搜索键、校区信息挪到导航行右侧（仅首页） |

## 3. 地址即页面

`#home/<channel>` 由 `pages/home.js` 自己解析（`routeChannel()`），路由层没有新增 route：

| 地址 | 页面 |
| --- | --- |
| `#home` | 全部好物（推荐） |
| `#home/books` `#home/living` `#home/electronics` `#home/sports` | 对应分类频道 |
| `#home/free` | 免费送（价格 0 过滤，不是分类） |
| `#forum/wants` | 校园求购（论坛求购板，另一张页面） |

- 频道按钮走新的 `home-channel` 动作：清空搜索词 → 写 `state` → `go('home/<key>')`。
- **排序不丢频道**：`feed-sort` 改成 `go(location.hash.slice(1) || 'home')`，在当前地址上重画。
- **筛选弹窗不丢频道**：`filter-form` 提交后跳 `home/<category>`。
- 浏览器返回键能在频道之间退回——这是「真的换了页面」最直接的证据，冒烟测试里专门断言了。

## 4. 视觉

- 频道磁贴：7 种底色（琥珀/珊瑚/薄荷/雾蓝/淡紫/粉/青），插画仍是 `category-art.js` 的内联 SVG，新增 `want` 一格（便签 + 放大镜）。
- 主视觉：左卡奶油黄渐变 + 三本书 + `¥18` 价签；右卡淡紫渐变 + 台灯与绿植。插画全部内联 SVG，不额外请求图片。
- 商品卡：圆角 18、留白放宽、价格用品牌红 `--price`、标签改成浅灰胶囊、收藏心形 hover 变粉。
- CTA 带：奶油黄 → 淡紫 → 薄荷的三段渐变，与两张主视觉卡呼应。
- 全部样式写在 `home.css`，选择器统一挂 `.home-page` / `.market-header-home`，不外溢到其他页面。

## 5. 删掉的东西（确认没有别处在用）

| 文件 / 符号 | 处理 |
| --- | --- |
| `src/components/rec-rail.js` | 删除 |
| `src/components/home-promos.js` | 删除（换成 `home-hero.js`） |
| `actions`：`rec-refresh` / `market-channel` / `market-shortcut` / `free-shelf` | 删除，统一为 `home-channel` |
| `index.html` 里 `home-promos.js` 的 modulepreload | 改为 `home-hero.js`，`home.css` 版本号 bump 到 `20261102-home-redesign` |

后端 `/products?rec=1` 与 `app/core/recommend.py` **没动**：接口还在，只是首页不再请求。

## 6. 验证

| 项 | 结果 |
| --- | --- |
| 前端单测 `node --test tests/*.test.mjs tests/*.test.js` | 48 项全过（新增 `home_hero.test.mjs`，删 `home_promos.test.mjs`） |
| 首页浏览器冒烟 `tests/home_browser_smoke.py` | PASS：双卡去处、七频道、无推荐轨、频道地址与返回键、分页/收藏/旧请求隔离、三个移动宽度 |
| Python 全量 `unittest discover` | 655 项，1 error 为 `test_public_demo` 缺 `PYTHONPATH`（单独加 `PYTHONPATH=.` 跑通过），与本次无关 |
| 视口实测 | 1440 / 768 / 390 / 320 均无横向溢出；320 头部收敛为两行（品牌+动作 / 搜索） |

## 7. 已知取舍

- 旧版专题卡的三组「关键词」（台灯 / 收纳 / 桌椅）没有再做成独立入口：它们和「宿舍生活」频道指同一批商品，按「一个去处只留一个入口」并入频道页。
- `state.homeLimit` 自 2026-10 起就只写不读（分页真实用的是 `PAGE_SIZE`），本次未清理，留给下一次死代码清理。
