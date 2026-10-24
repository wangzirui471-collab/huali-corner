# 本轮 skill 的选择与适用范围

日期：2026-10-21。用户要求使用新下载的 skill，优先优化前端。

## 已采用：ui-ux-pro-max

来源：本机 `.codex/skills/ui-ux-pro-max/SKILL.md`。项目的 `04-界面设计与体验规范.md` 继续作为品牌与布局的权威规范。

- 首次查询 `campus resale marketplace clean --design-system` 得到宣传页 Hero/Testimonials/CTA，和校园二手商品流不符，未采用。
- 按 skill 要求收窄并重试一次：`secondhand product discovery marketplace --design-system`，命中 Marketplace / Directory。采用搜索与分类优先、清晰商品信息、可见筛选、轻量视觉和键盘支持。通用蓝绿配色、外部英文字体及大 Hero 不适用于现有品牌，未覆盖项目的紫色标识、暖黄操作色、中文系统字体、紧凑双专题和五槽导航。
- `responsive forms component boundaries --stack vue` 提供 Vue 组件及表单指导。现有 Element Plus 已提供校验能力，不另加表单库。
- `error summary validation --domain ux -n 3` 命中错误汇总、朗读及字段关联：仅在提交失败后聚焦汇总，提供直达字段的链接，同时保留字段旁错误与已填内容。

当前是现有组件样板的定向改进，没有生成另一份与 04 竞争的品牌规范。响应式、焦点、文字对比、错误恢复和减少动效需通过实际页面检查，不能凭 skill 推荐声称验收。

## 已采用：tdd

来源：本机 `.codex/skills/tdd/SKILL.md`，已阅读附属 `tests.md`、`mocking.md`。

按 skill 的测试入口确认要求询问用户后，用户选择“优先验证前端界面”。本批通过页面可见 DOM、表单提交与焦点验证交互，不读取组件内部状态、不 mock 控件库、不把样板成功当成真实商品发布。每次先运行一个失败的行为测试，再实现最小行为。

## 暂未完整执行：improve-codebase-architecture

该 skill 要求先调用 `codebase-design`，随后以子代理扫描、HTML 候选报告和用户选择进入 `grilling`，并使用 `domain-modeling` 维护术语。当前本机未发现这三个依赖 skill。该独立评审流程暂未启动，不能声称已完成它的架构评审；继续按六份重构文档推进已授权的实现与 UI 工作。

`find-skills` 用于了解技能发现方式；本轮已找到适用的本地 UI/UX skill，没有为凑齐工具而安装其他技能。

## 2026-10-23 首页独立评审与用户确认后应用

本机 ui-ux-pro-max：先读完整 SKILL.md，`campus marketplace compact browsing --design-system` 偏宣传页，收窄为 `marketplace directory --domain product` 匹配 P2P Marketplace 与 Directory。采用商品发现、筛选和清楚卡片层级；不覆盖 04 已确认的紫色/暖黄/中文系统字体。

`carousel pause controls --domain ux` 命中自动内容暂停、前后控制、焦点/悬停/减少动态效果；`error summary validation --domain ux` 命中字段错误关联，后者保留为后续发布表单切片建议。本轮不新增表单库。

实际使用的测试 skill 为 `.codex/skills/test-driven-development/SKILL.md`；正式新增 9 个行为用例，按失败证据补齐轮播、追加恢复、收藏和媒体边界。先做 artifacts 中独立 Vue 预览，用户确认后才修改业务组件；视觉检查使用浏览器和合成接口，不将它等同真实业务验收。

### 2026-10-24 页面辨识度候选

继续使用本机 UI UX Pro Max。`visual hierarchy grouping --domain ux` 返回 hover、面包屑和标题层级，不能作为论坛布局的精确匹配；收窄为 `forum discussion --domain product`，首项命中 Forum / Discussion Board，采用 feed/thread、板块与信息对齐建议。只在论坛标题区域使用深紫，保留项目原定紫色 ZJ、暖黄操作色和中文系统字体，不把通用深色建议直接覆盖整站。

按 TDD 先验证两项新交互失败，再实现独立评审副本；追加失败保留草稿回归。最终仅报告独立预览测试、候选类型和构建结果。浏览器访问策略阻止本轮视觉观察，不补写截图或手机验收通过。
