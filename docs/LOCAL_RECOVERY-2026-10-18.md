# Windows 本地恢复记录

正式项目：`D:\zi\huali-corner-trial`。本地地址：<http://127.0.0.1:8081/>。8081 使用原有 `var-trial/market.sqlite3`；没有改用检测包或空库。

启动修复来自 `fix/windows-trial-launcher @ 08db9f8`。可运行的基础解释器为 `C:\Program Files\Python312\python.exe`（3.12.5）。已用原项目离线包校验 SHA256 后建立 `.venv-trial/`，固定 Pillow 12.3.0、PyMySQL 1.2.3，不修改系统 Python。

启动器位于根目录 `start-trial-8081.bat`。它通过 `scripts/launch_trial.py` 探测真实可运行解释器，保留原数据路径与环境变量，不强制杀死占端口进程。电脑重启后须重新运行；未设置开机自启。

本次恢复前后，原试用库均为 7 个账号、6 件商品、1 笔订单，SQLite quick_check 为 ok；这只是数量及完整性核验，不等于所有业务已逐条验收。首页、前端入口、健康、配置、商品接口均返回 200；启动器 6 项测试通过。

一致性数据库备份及原启动文件位于 `_backup-launcher-20261018-114347/`，在 Git 忽略范围内。原第一版 BAT 另有 stash：`preserve local first launcher before 08db9f8`。不要直接恢复 stash 覆盖当前启动器。

后台运行日志位于 `_local-run/`。原启动修复 ZIP 与说明现保存在 `_local/startup-repair/`，固定的 `repair-wheels/` 目录维持原位以供 helper 使用。

Cloudflare 本机 OAuth、远程 D1 的 SELECT 1、R2 只读访问已确认可用；Windows Workers HTTP 探针的远程绑定、Web Crypto 及 Pillow 12.2.0 图片检查通过，但原生密码函数检查失败。业务固定 Pillow 12.3.0 与该探针的 12.2.0 不同，目标制品源返回 403，不能宣称业务迁移验收通过。没有发布正式 Worker 或初始化业务表。

以上为本机恢复当时的检查记录。Cloudflare 另有并行开发，本次整理未验证其新增适配代码；依赖源连通性及部署进展以最新 [Cloudflare 实测状态](CLOUDFLARE_ACCESS.md) 为准，不用早前的 403 检查覆盖后续实测。
