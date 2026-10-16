'use strict';
// 基础设施层 · 静态资源路径
// 公开演示版会被托管在子路径下（例如 /preview/），以 / 开头的绝对路径
// 会指到站点根目录去，那里的 assets 并不存在，所以统一补一个点走相对路径。

export const asset = path => (window.HUALI_STATIC_DEMO ? '.' : '') + path;
