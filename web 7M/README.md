# 当前网页版前端

Vue 3 + Vite + Vue Router + Pinia。当前页面仍使用原模板和交互，由 Vue 页面适配器管理生命周期；这是框架接入，不是替换界面。原 AI 三模式、宠物资源、权限和业务 API 保留。

## 开发

要求 Node `^20.19.0 || >=22.12.0`，推荐 Node 24。在本目录执行：

```powershell
npm ci
npm run dev
```

开发入口为 `http://127.0.0.1:5173`。先启动使用全新合成数据目录的本机后端；`/api` 和 `/media` 默认代理至 `http://127.0.0.1:8081`。可用 `HUALI_DEV_API_ORIGIN` 指定其他本机 HTTP 地址，远程地址会被拒绝。不要用旧 Worker 的 `remote:true` 配置做本机联调。

## 构建和本机集成

```powershell
npm run build
npm run preview
```

产物在本目录 `dist`，预览端口 4173。预览只提供静态资源；需要业务 API 时使用开发代理，或让原 Python 服务通过已有 `--web "<绝对路径>/web 7M/dist"` / `HUALI_WEB_DIR` 提供产物。不要直接由普通静态服务器提供含 SFC 和裸导入的源码目录。

Worker 配置的静态目录已指向 `dist`。用户随后授权三端同步，已用保留线上197原模块和绑定的候选流程发布，详见 `docs/THREE-END-SYNC-2026-11-12.md`；没有运行旧 remote:true 配置或迁移真实数据库。本地使用合成数据，模型密钥缺失时原 AI 自动回退规则回答。

## 测试

```powershell
npm test
npm run test:unit
# 已提供 playwright-core 和浏览器时：
$env:HUALI_PLAYWRIGHT_MODULE='你的 playwright-core 绝对路径'
$env:HUALI_BROWSER_EXECUTABLE='你的 Edge 或 Chromium 绝对路径'
npm run test:browser
```

`npm test` 构建后执行全部 17 个前端/小程序脚本，包括 Pinia、路由和 153 原静态资源字节检查。浏览器测试全部使用合成 API，不登录生产账号或调用真实模型；原网页对照样本缺失时，从固定基线提交只读恢复到忽略的 artifacts 目录。`HUALI_DEV_ORIGIN` 可额外检查已运行的 Vite 开发服务。

原分享链接 `#staff`、`#home/books` 仍可打开；Vue Router 导航规范为 `#/staff`、`#/home/books`。CSS、原图片地址和样式加载顺序保持不变；现有 CSS 通过静态透传保留浏览器原容错行为。

结构：`src/main.js` 装配，`src/framework/App.vue` / `LegacyPage.vue` 稳定挂载，`framework/router.js` 路由，`framework/store.js` 唯一 Pinia，`framework/runtime.js` 账号初始化与预热。原 `core/state.js` 是同一 store 的兼容出口。

限制：本轮保留 body 上原 AI 单例，常规切页不会销毁它；整应用卸载/HMR 尚不完全释放其原定时器和观察器。未进行微信真机或真实账号验收。
