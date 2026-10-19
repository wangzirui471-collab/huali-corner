/**
 * 华立转角 — Cloudflare Worker 反向代理
 *
 * 作用：把 `zhuanjiao.wangzirui471.workers.dev` 收到的所有请求
 * （前端静态页 + /api/* 接口）原样转发到「这份 Python 后端」(Backend mission/server.py)。
 *
 * 为什么这样最简单：
 *   - Python 后端自身就能同时提供 web 7M 静态文件和 /api 接口（同域）。
 *   - 前端用相对路径 /api/... 调接口，经本代理同域转发后无需任何改造。
 *   - 之后在本仓库改任何功能（论坛/社区拆分、好友、选学院年级…），只要重新托管
 *     Python 后端并重启，链接立即生效，不用再维护第二套代码。
 *
 * 数据说明：切换后，链接背后的数据库是「Python 后端自己的库」（SQLite/MySQL），
 * 与旧 Worker 里 Cloudflare D1 中已有的商品/账号不互通，需要单独做数据迁移或重新开始。
 */

export default {
  async fetch(request, env, ctx) {
    const backend = env.BACKEND_URL;
    if (!backend) {
      return new Response('BACKEND_URL 未配置：请在 Worker 环境变量里设置 Python 后端的公网地址', { status: 500 });
    }

    const url = new URL(request.url);
    // 目标地址 = 后端基地址 + 原路径 + 原查询串
    const upstream = new URL(url.pathname + url.search, backend);

    // 透传客户端 IP（供后端 --trust-proxy 下的限流/绑定使用）
    const headers = new Headers(request.headers);
    const cfIp = request.headers.get('cf-connecting-ip');
    if (cfIp) headers.set('X-Forwarded-For', cfIp);
    headers.set('X-Forwarded-Proto', 'https');

    const init = {
      method: request.method,
      headers,
      redirect: 'follow',
    };
    // GET/HEAD 没有请求体
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      init.body = request.body;
    }

    try {
      const resp = await fetch(upstream.toString(), init);
      // 透传状态码与响应头，流式转发响应体（含上传/下载）
      return new Response(resp.body, resp);
    } catch (err) {
      return new Response('后端不可达 (' + backend + ')：' + err.message, { status: 502 });
    }
  },
};
