# 华立转角 Vue 前端候选

手写 JavaScript + Vue 3 + Element Plus，Node.js 22.12+。本轮覆盖 T03–T07 前端页面，完整阶段、浏览器和平台验收仍未完成。默认保留旧 `/api/*`；可显式设置 `VITE_HUALI_COMPAT_API=1`，把已实现的身份/订单操作切到新 FastAPI `/api/v1/compat/*`，底层仍为同一个旧 writer。其他领域不切换。

新前后端与智能客服完整接手见 [给下一位 AI 的交接](../../docs/refactor/AI-TAKEOVER-AND-INTEGRATION.md)。该开关在 Vite 开发启动或构建时生效，不能在构建后临时改变；必须另启 8001 新 API 与 8081 隔离旧服务。5198 界面评审不启用这个真实业务开关。

完整换机说明、隔离数据启动、接口边界和测试清单见 [前端候选换机手册](../../docs/refactor/FRONTEND-TRIAL-HANDOFF.md)。

```powershell
npm ci
npm run dev
```

开发入口 `http://127.0.0.1:5173/`，组件样板 `/_dev/components`。旧业务 API 默认代理本机 8081，新 `/api/v1` 代理本机 8001。业务预览需要单独启动隔离旧服务，不使用真实数据库或旧 remote:true 配置。

| 命令                    | 用途                                  |
| ----------------------- | ------------------------------------- |
| `npm run lint`          | ESLint、中文方法注释、Prettier        |
| `npm run typecheck`     | JavaScript/checkJs 与 Vue 模板        |
| `npm run test:unit`     | 协议、身份/取消、恢复、控件与页面行为 |
| `npm run build`         | 默认构建，保持业务未上线              |
| `npm run build:preview` | 仅组件样板的隔离构建                  |
| `npm run build:trial`   | 业务前端候选，输出 dist-trial         |
| `npm run preview:trial` | 本机 4173 预览业务候选，含回环代理    |
| `npm run generate:api`  | 从新服务端 OpenAPI 生成声明           |

`shared/legacy` 保留旧数组/数字编号、Bearer 会话与唯一业务 writer；`shared/http` 保留新 v1 封套协议。页面通过 `useLegacyApi` 绑定身份和生命周期，500/HTML 不清会话，401 明确退出。只有同源允许媒体会尝试认证 Blob，离开时释放。

品牌令牌、紫色 ZJ、暖黄操作、独立双专题和手机五槽保留。响应式规则已写，业务页面四尺寸截图仍由另一台电脑验收；旧组件截图不能替代本轮业务视觉证据。所有手写函数加中文 JSDoc，生成 `.d.ts` 不手改。
