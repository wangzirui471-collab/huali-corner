# 当前网页版修复验证记录（2026-11-12）

## 基线与保存

正式版本93f6eec7、main609bd56；初始82资源内容与main一致，215公开资源完整核对，197后端模块只读备份。原始文件及清单在忽略目录 `artifacts/current-web-audit-20261112/`；没有把模型密钥、私密媒体、真实库或验收截图上传GitHub。

## 先失败后修复

- 新增正文截止时间用例在修复前失败：设25ms超时但等到120ms后成功；新增普通登录超时提示用例也失败，错误被误称“AI响应超时”。修复后两项通过，成功后无迟到取消亦通过。
- 真实本机页面启动时 `/me` 返回HTML401，390宽度原会话被清除；修复后保留。JSON401仍正确退出，不放宽后端认证。
- 真实AI窗口客服模式返回合成503后，问题输入从非空变空，测试失败。客服/办公/工作三处修复后，四屏宽均保留原问题；额外测试等待时新输入不会被覆盖，请求不会自动重发。
- 浏览器最初合成配置漏了页面就绪所需name，导致停在“正在打开转角”；补齐测试夹具，未改产品页面来迁就测试。

## 实际通过的检查

| 检查 | 实际结果 |
| --- | --- |
| 当前Web/小程序14个 `.test.mjs/.test.js` 脚本逐一执行 | 14通过，0失败 |
| 原5项传输合同+新3项正文/提示/清理回归 | 8项通过 |
| `test_cloudflare_auth_complete.py` | 13项通过，内存合成数据，0.331秒 |
| `test_cloudflare_pages.py` | 8项通过，合成页面接口 |
| 390/1440浏览器启动 | HTML401保留登录，JSON401清登录，均通过 |
| 390/1440登录与注册HTML响应 | 600000轮KDF实际执行，异常显示中文提示，表单保留，无原始JSON报错 |
| 360/390/768/1440 AI窗口 | 三模式原地切换、失败问题恢复、新草稿保留、无自动重发、窗口边界、放大还原、60%—160%大小、pageerror为0 |
| 运行代码语法与差异检查 | Node --check与git diff --check通过 |

## 可复跑命令

```powershell
node --test tests/site_transport.test.mjs tests/site_transport_deadline.test.mjs
# 使用已有Playwright-core模块和系统Edge；也可通过HUALI_BROWSER_EXECUTABLE指定已有浏览器。
$env:HUALI_PLAYWRIGHT_MODULE = '本机已有的playwright-core绝对路径'
node tests/current_web_login_browser_smoke.cjs
node tests/current_web_pet_browser_smoke.cjs
python -B -X utf8 -m unittest discover -s tests -p test_cloudflare_auth_complete.py -v
python -B -X utf8 -m unittest discover -s tests -p test_cloudflare_pages.py -v
```

浏览器脚本所有API均由同一个本机合成服务器返回，不代理生产请求；AI固定合成失败，不连接收费模型。项目依赖仍为Pillow12.3.0/PyMySQL1.2.3；使用既有项目独立解释器，没有装全局依赖或复制node_modules/虚拟环境。

## 未验证与恢复

没有真实账号、真实供应商、微信真机或全部旧业务写链路验收；未跑完整旧后端全套，不拿历史结果代替本轮。旧截图中的501接口缺失无法据当前版本直接重现；当前页面接口合同8项通过，但不能据此承诺每个生产账号/订单路径都已逐一操作。

发布范围以 `static-stage-manifest.json` 为准：215静态文件只变3个JS，212项保留原字节；197后台模块完全不改。上传、预览、切流必须分别记录，连接中断不代表切流成功，不能降低TLS校验。若未得到有效发布回执，正式站仍应按原93f6eec7描述。
