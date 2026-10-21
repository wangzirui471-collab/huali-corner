# JavaScript + Vue 3 + Element Plus 骨架

要求 Node.js 22.12+。在本目录运行：

```powershell
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173/_dev/components`。样板包含 Element Plus 按钮、输入框、表单、标签、持久反馈和键盘弹窗，以及六类页面状态。表单支持提交校验、错误汇总聚焦、链接定位字段、修正后反馈，并保留输入。品牌 SVG 复制自旧客户端源素材；没有测试账号或真实业务写入。端口被占用时可用 `npm run dev -- --port 5186`。

| 任务命令                | 执行内容                              |
| ----------------------- | ------------------------------------- |
| `npm run lint`          | ESLint 与 Prettier 检查               |
| `npm run typecheck`     | JavaScript JSDoc 与 Vue 模板类型检查  |
| `npm run test:unit`     | HTTP 异常、迟到响应和基础控件行为测试 |
| `npm run build`         | 默认构建，关闭开发样板路由            |
| `npm run build:preview` | 显式隔离预览构建，开放样板路由        |
| `npm run generate:api`  | 从服务端 OpenAPI 生成 DTO 类型        |

API 代理只指向本机 8001 的新骨架。组件不直接 fetch；HTTP 统一处理同源凭据、幂等键、CSRF 头、未知写入结果和错误封套。账号切换及页面销毁时调用 RequestScope.reset，使已取消或迟到响应不能污染新上下文。登录模块后续负责明确 401 的身份处置，5xx 不自动清会话。

所有手写方法用中文 JSDoc 说明用途；生成文件不手工改。当前未实现业务页面，未接入生产 API，完整首页、五槽导航和旧 hash 兼容在 T03 业务切片验收。

新装 skill 的使用与取舍见 `docs/refactor/skill-usage.md`。Vitest 对 Element Plus 启用 inline 转换，避免原生 Node 的 CJS 默认导出使 async-validator 失效；不要通过 mock 校验或删掉失败断言绕过此配置。

手写源代码全部使用 JavaScript。TypeScript 仅作为开发检查工具；`generated.d.ts` 由 OpenAPI 自动生成，仅供编辑器检查与提示，不是 TypeScript 业务实现。
