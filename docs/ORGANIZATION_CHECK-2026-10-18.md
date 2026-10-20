# 文件整理与验证记录

日期：2026-10-18。分支：`chore/project-organization`，基于已恢复的 `fix/windows-trial-launcher @ 08db9f8`。未提交、推送、合并或部署。

## 本轮改动

- 将 6 个无正式引用的本地旧后端文件及旧网页 app.js 归档到 `_local/legacy-flat/`，保留原字节。
- 将原启动修复 ZIP 和说明保留到 `_local/startup-repair/`；repair-wheels、.venv-trial、启动 BAT 位置不变。
- 用户提供的 Word 规范与 Markdown 需求原件不改，复制到 docs/standards 和 docs/references，并核对 SHA256。
- 增加文档导航、项目结构、规范适用说明、后端建议和本地恢复记录；修正根 README 中旧 seed.py 路径。
- `_local/` 与 `_local-run/` 加入 .gitignore；没有移动或提交账号库、图片、备份和口令。

归档清单在本机 `_local/organization-manifest.json`，逐项记录原位置、新位置和 SHA256。9 个文件校验全部一致；整理脚本核对 211 个受保护的已跟踪文件未改动（排除本轮有意修改的 README 与 .gitignore）。

## 实际验证

在 Windows Python 3.12.5、项目 .venv-trial（Pillow 12.3.0、PyMySQL 1.2.3）运行：

```powershell
& '.\.venv-trial\Scripts\python.exe' -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

结果：294 项运行，287 项通过，7 项 ERROR，耗时 213.141 秒；不是全量通过。检查从文件整理前开始，结束于整理后，不构成同环境前后两次全通过的对照。

| 报错 | 数量 | 现场证据与处理 |
| --- | ---: | --- |
| 静态资源符号链接逃逸测试 | 1 | Windows 无创建符号链接权限，WinError 1314；未修改系统权限或跳过断言 |
| 降权测试清理临时 SQLite 文件 | 5 | WinError 32；测试连接未显式关闭，文件仍被占用；生产降权实现已有 closing，本轮均未改动 |
| 降权命令输出文本检查 | 1 | 子进程非 UTF-8 输出触发 UnicodeDecodeError，stdout 未正常取得；待统一编码约定 |

客户端现有检查：

```powershell
node tests/frontend_modules.test.mjs
node tests/user_center.test.mjs
node tests/native_client.test.js
node tests/native_order.test.js
node tests/native_trial_auth.test.js
```

以上 5 个脚本全部退出码 0。其中前端模块检查实际加载 44 个模块；该检查只能证明其导入和入口可用，不能单独证明所有依赖无环或全部界面操作正确。

新导航链接检查通过；原始参考副本中的历史相对链接未改写。归档文件逐项 SHA256 复核通过。

整理后真实 8081 `/api/health` 返回 `{"ok":true,"trial":true}`。本次不进行注册、模拟支付等向原库写入测试记录的操作，未重启或停止正式服务。没有本轮浏览器完整交互、微信真机、公网业务或 Cloudflare 新适配验收。

## 并行改动

整理过程中发现 `docs/CLOUDFLARE_ACCESS.md` 更新和 `Backend mission/app/cloudflare/` 新增；它们不由本轮整理脚本写入或验证，已原样保留。未将其混入本轮完成声明，未尝试回退或覆盖。
