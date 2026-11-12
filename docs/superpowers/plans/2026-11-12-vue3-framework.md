# 当前网页版 Vue 3 框架接入实施计划

**Goal:** 原样保留当前界面与 AI，接入 Vue 3、Vite、Vue Router、Pinia。

**Architecture:** Vue RouterView 的稳定页面适配器调用原页面渲染；Pinia 单一 store 保持 state 兼容；Vite 构建入口与复制原静态资源。

**Tech Stack:** JavaScript、Vue 3.5、Vue Router 4.6、Pinia 3、Vite 8、Playwright / Edge、node:test。

**Spec:** `docs/superpowers/specs/2026-11-12-vue3-framework-design.md`

## 约束与检查重点

保留模板、CSS、照片、AI 和后端；不使用十月候选覆盖。新增函数中文 JSDoc；项目独立依赖，不装全局工具。重点覆盖旧 hash、同路由刷新、切页期间异步响应、切换账号和 AI 跨页保留。所有联调使用合成数据。

## 任务

### 1. Pinia 与 Vite 基础

- [x] 保存原网页与登录 / AI 浏览器基线（全部通过）。
- [x] 新增 `tests/vue_framework.test.mjs`，先验证 Pinia 唯一状态及路由合同失败。
- [x] 在 `web 7M/package.json`、`vite.config.js` 和 `src/framework/store.js` 建立独立框架依赖与构建。
- [x] 将 `core/state.js` 原 state 导出迁为同一 Pinia store，保留全部辅助函数。

### 2. Vue 生命周期与路由

- [x] 新增 `App.vue`、`LegacyPage.vue`、`src/framework/router.js`；原 main 初始化提取为可释放生命周期的 runtime。
- [x] `core/nav.js` 使用 Vue Router 导航，同页 go 仍重新渲染；原页面读取 hash 支持 `#name` 和 `#/name`。
- [x] 保留原鉴权与 renderId，移除重复 hashchange 渲染来源，监听器提供释放。
- [x] Vite build 与路由 / 状态单测通过。

### 3. 行为与视觉回归、交付

- [x] 现有浏览器测试支持 dist 目录，原登录及四屏宽 AI 测试重跑。
- [x] 新增浏览器路由、Pinia、同页刷新、历史、未知链接和原站对照检查；检查开发服务。
- [x] 原前端测试全量、build、CSS / 图片字节与后端零 diff 检查。
- [x] 更新交付手册与验证记录，提交本机分支；按本次授权先交付可验收结果，不擅自发布框架切换。

## 执行记录

采用当前会话直接实施，不分派子代理。用户已有明确框架和保留要求，例行实现选择由执行者处理，不重复请求确认。

最终证据：npm test 17 个脚本无失败，框架合同 6 项；最终浏览器 32 页面/角色对照、8 登录场景、4 屏 AI、Vite 开发与手动重试通过；公开演示 3 Python 合同和子目录浏览器通过。
独立只读审查发现并修复排序、失败卡片和演示编译接线；一项轻微限制（整应用卸载的旧 AI 单例清理）保留在验证记录。后端仅静态目录配置变化，无 Python/AI/交易实现变化；本轮未上线。
