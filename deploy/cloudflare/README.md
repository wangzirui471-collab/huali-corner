# 华立转角 — 让链接改用本仓库 Python 后端

把 `zhuanjiao.wangzirui471.workers.dev` 变成「纯反向代理」，把所有流量（前端 + `/api`）转发到
本仓库的 Python 后端（`Backend mission/server.py`）。这样本仓库做的任何改动，只要重启托管的
Python 后端，链接立即生效，不再需要维护第二套代码。

## 前置条件（两项，需用户/账号所有者提供）

1. **Cloudflare 部署权限**：账号 `wangzirui471` 的 Workers 编辑权限。
   - 方式 A：给我一个仅授权 Workers Scripts 的 `CLOUDFLARE_API_TOKEN`，我用 Wrangler 部署；
   - 方式 B：你在 Cloudflare 后台把 `worker.js` 内容粘贴进 `zhuanjiao` 这个 Worker 的编辑框。
2. **一个公网可达的 Python 后端地址（BACKEND_URL）**：
   - 推荐用 Render（仓库已带 `Backend mission/render.yaml`，启动命令 `--trial --host 0.0.0.0 --trust-proxy`，
     数据目录 `HUALI_DATA_DIR=/var/data/huali`）。Render Starter + 1GB 持久盘为付费资源，需账号所有者确认账单。
   - 或你自己的常驻机器（需稳定公网地址，临时隧道每次重启会变，不适合长期链接）。

## 部署步骤

```bash
# 1) 安装 Wrangler（如有 API Token）
npm i -g wrangler
wrangler login   # 或 export CLOUDFLARE_API_TOKEN=...

# 2) 设置后端地址（用 secret 更安全）
cd deploy/cloudflare
wrangler secret put BACKEND_URL   # 输入 https://你的-python-后端地址

# 3) 部署
wrangler deploy
# 部署到已有的 zhuanjiao 脚本即覆盖旧 Worker，workers.dev 地址不变
```

无 Token 时：在 Cloudflare 后台 `zhuanjiao` Worker 编辑器里直接粘贴 `worker.js`，
并在 Variables 里加 `BACKEND_URL`。

## 数据迁移提醒

切换后链接背后是 Python 后端自己的库（SQLite/MySQL），与旧 Worker 里 Cloudflare D1 中
已有的商品/账号**不互通**。需要：要么把 D1 现有数据导出后导入新库（需单独脚本），要么重新开始。
不要直接覆盖一份已经有同学发布内容的新库。
