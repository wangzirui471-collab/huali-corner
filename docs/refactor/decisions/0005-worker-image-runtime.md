# 0005：图片算法可本地运行，Worker 依赖版本尚不具备生产结论

日期：2026-10-22。状态：本地能力已验证；生产运行位置待 T01 验收。

## 观察

- 新 API 使用 Pillow 12.3.0；当前 Worker SDK 的 Emscripten 索引未解析到该版本的兼容 wheel。
- 隔离探针锁定 Pillow 12.2.0，已实际运行 JPEG/PNG/WebP、EXIF 旋转与移除、头像缩放、20M 像素、5 MiB 字节、超限/截断/动画拒绝，以及 R2 回读。
- 探针通过 `sync_sources.py` 复制新 API 的同一图片适配器白名单源码，不另维护算法。复制目标是忽略目录，重新启动前需要同步。
- Pillow 12.3.0 的[官方发行说明](https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html)包含安全修复。12.2.0 的本地成功不能证明它适合作为面向用户上传的生产依赖。

## 决定

正式 API 保留 12.3.0，12.2.0 仅用于本地合成能力探针。图片适配器在解析前限制为 JPEG、PNG、WebP，限制字节和像素，拒绝多帧并重编码清除元数据；这些限制不能替代完整的依赖安全核查。

下一阶段先验证维护中的兼容 wheel/运行时，或按 02 的既定备选验证共享 Python 包的外部 FastAPI 路线。真实平台 CPU、峰值内存、并发和认证读取未通过前，不开放正式上传、不决定 Worker 已可承担全部图片处理，也不降低密码轮数。

20M 压测使用纯色合成图；5 MiB 样例用 JPEG 尾部填充独立测试请求缓冲。它们不是任意复杂照片、真实云端内存或线上性能的证明。

## 2026-10-22 换机核对补充

正式 API 的锁定依赖仍为 12.3.0，未在本轮擅自升级；本机 Conda CPython 3.13.12 的独立新 API 环境已实际运行 17 项测试、Ruff 和 mypy。Worker 探针仍锁 12.2.0，仅限合成数据。

图片运行位置继续沿两条既定路线核对，不新增业务 writer：

1. Worker 主路线须先通过锁定 SDK 的 Pyodide 兼容 wheel 解析，再验证同一图片适配器、资源预算及认证媒体。不以 Windows CPython wheel 成功安装代替 Emscripten wheel 验收。
2. 如果维护中的安全版本在 Worker 仍不可用，按 02 §2 评估共享 Python 包的外部 FastAPI 路线；D1 仍经受保护的窄 Worker 边界，需另验服务间认证、重放保护和原子性。本轮没有启用该备选、部署服务或接入真实上传。

本轮核对的 SDK 1.17.8 源码在当前兼容日期选择 `cpython-3.14.2-emscripten-wasm32-musl`，兼容索引为 `https://index.pyodide.org/314.0.7`。直接读取该索引的 `/pillow/` 返回 HTTP 403；这只能证明本次索引访问失败，**不能更新为“当前索引仍只有 12.2.0”或“12.3.0 已受支持”**，解析结果以之后实际 SDK 同步为准。平台包限制参考 [Cloudflare 官方包说明](https://developers.cloudflare.com/workers/languages/python/packages/)。

另发现 [Pillow 13.0.0 官方发行说明](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)已在 2026-10-16 发布，包含 JPEG 解码及 EXIF 等安全修复。图片运行时门槛应加入该版本安全公告与本项目 JPEG/PNG/WebP 路径的适用性核查；**12.3.0 是当前工程锁定值，不是本轮确认的生产安全结论**。正式依赖升级及兼容回归另作明确切片，不能以本轮合成测试通过代替安全核查。
