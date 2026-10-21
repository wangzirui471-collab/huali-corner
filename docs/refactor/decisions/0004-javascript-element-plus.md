# 0004 前端采用 JavaScript 与 Element Plus

日期：2026-10-21。状态：用户已确认，覆盖原计划的前端 TypeScript 选型。

## 用户要求

用户要求使用 JS 重构并加入 Element UI，随后明确选择：前端 JavaScript + Vue 3 + Element Plus；后端继续 Python/FastAPI。所有任务、函数和方法保留中文说明。

## 决定与落地

- 手写前端使用 `.js` 和无 `lang="ts"` 的 Vue 单文件组件；不要求用户阅读 TypeScript 业务源码。
- Vue 3 使用配套的 Element Plus。按钮、输入框、表单、提示、标签和弹窗已实际接入，通过 shared/ui 统一品牌和行为；不混用第二套 UI 框架。
- JSDoc 同时说明用途、参数与返回结果；`checkJs` 和 `vue-tsc` 检查 JavaScript 及模板。TypeScript 仅作为开发检查工具，OpenAPI 自动生成的 `.d.ts` 仅提供编辑提示，不参与业务运行。
- ESLint 对手写具名函数和类方法执行中文 JSDoc 检查。匿名回调由所在步骤说明用途；关键权限、事务、账号切换和失败恢复保留原因注释。
- 旧 Web、小程序、API 和实际数据库兼容边界继续遵守 0002。前端语言变更不改变交易规则和 Python 领域架构。

Element Plus 的 [快速开始](https://element-plus.org/en-US/guide/quickstart.html)支持显式引入；本工程按使用的组件加载样式，品牌令牌通过专用适配文件配置。实际版本由锁文件固定。

## 验证

当前 Vue 样板在 Windows 中文/空格路径下完成 JavaScript/模板类型检查、9 项 Vitest 测试和默认构建。浏览器已验证打开弹窗、Escape 关闭与焦点恢复；视觉证据和剩余门槛见 verification.md。业务页面迁移仍按后续阶段验收。
