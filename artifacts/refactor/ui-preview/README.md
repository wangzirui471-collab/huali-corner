# 独立界面评审宿主

本目录的源码、配置和合成公开素材已随本次交付显式纳入 Git；依赖、dist、运行日志、临时截图和数据库不纳入。它仅用于评审校园社区、论坛、消息和订单的视觉方向，尚未把这些布局覆盖到正式业务组件。

从项目根目录先安装 `apps/web` 的锁定依赖；需要 Node 22.12+。不单独安装全局环境。

```powershell
# 本宿主只使用合成数据，不启用真实 FastAPI 业务开关。
$env:VITE_HUALI_COMPAT_API = '0'
node apps/web/node_modules/vite/bin/vite.js build --mode trial --config artifacts/refactor/ui-preview/vite.config.js
node apps/web/node_modules/vite/bin/vite.js preview --config artifacts/refactor/ui-preview/vite.config.js --host 127.0.0.1 --port 5198 --strictPort
```

打开 http://127.0.0.1:5198/，顶部可以切换四个评审页。该宿主拒绝业务发送、发布和交易，收藏只在内存变化；不要将其当成真实后端验证。实际前后端联调按 `docs/refactor/AI-TAKEOVER-AND-INTEGRATION.md` 启动 5173/4173、8001、8081。

从项目根运行预览用例：

```powershell
node apps/web/node_modules/vitest/vitest.mjs run --config artifacts/refactor/ui-preview/vite.config.js
```

`src/pages` 是独立评审副本，正式候选在 `apps/web/src/features`。用户确认设计后应按切片迁移模板及样式，避免长期维护两套业务行为。
