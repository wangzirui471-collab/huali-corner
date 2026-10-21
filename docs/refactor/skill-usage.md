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
