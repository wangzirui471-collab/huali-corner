# U03 网页接线合同

2026-10-17。B 已编写页面、组件、动作、样式及测试源码，尚未运行或取得截图。
用户要求本机不创建数据库、不运行测试；由 A/用户在自己的环境完成接线与验收。

## 1 文件与依赖

| 文件 | 职责 |
| --- | --- |
| src/pages/me.js | 我的转角与公开主页，保留原 profile/mine 导出 |
| src/components/user-profile.js | 资料表单、展示、头像表单与冲突对照HTML |
| src/components/user-avatar.js | 安全的本站头像路径、默认头像HTML |
| src/actions/user-profile.js | user- 命名空间的 clicks/submits、头像 change/error 处理 |
| user-center.css | .user-center 内的布局、头像、表单与移动端样式 |

页面不 import router 或动作文件。JSON 请求继续使用 core/http.js，不新增全局登录状态。
更新后的共享资料仅写 state.me；待保存文本留在表单，不新增 localStorage 缓存。
头像 blob URL 登记进已有 state.mediaURLs，继续由原 router.releaseMedia 清理，取消/替换预览也会释放。

## 2 A 注册动作和事件

在 `src/actions/index.js` 导入：

```javascript
import * as userProfile from './user-profile.js';
```

把 `...userProfile.clicks`、`...userProfile.submits` 分别加入既有分发表，保留其他领域原条目。
在 registerActions() 中且只注册一次：

```javascript
document.addEventListener('change', userProfile.avatarFileChange);
document.addEventListener('error', userProfile.avatarImageError, true);
```

error 必须使用捕获阶段，因为 img error 不冒泡。
change 钩子不能遗漏：用户重新选文件后，旧上传的“确认设为头像”必须立即失效，不能误确认上一张。
这两个导出自身只处理用户中心对应元素，不影响其他表单或商品图。

| 类型 | 名称 |
| --- | --- |
| submits | user-profile-form、user-avatar-form |
| clicks | user-profile-compare、user-profile-keep-input、user-profile-reset |
| clicks | user-avatar-preview、user-avatar-confirm、user-avatar-remove、user-avatar-cancel |

新表单不再生成原 profile-form。旧 actions/account.js 的原处理可以保留供兼容，B 不修改或重复注册它。
不要把 user- 写操作加入公开静态演示的允许列表；原演示限制继续有效。

## 3 样式、路由与静态演示

在 index.html 的原 styles.css/market.css 之后追加 user-center.css 引用，沿既有缓存版本号方式管理。
router.js 现有 profile(id)/mine 路由不需要改名；不要注册另一套路由或入口。
styles.css/market.css 不需要 B 的全局覆盖；新增规则均位于 .user-center。

A 还须把 user-center.css 加入 `scripts/build_public_demo.py` 的静态复制清单。
脚本原来只复制 public-demo.js、styles.css、market.css，漏复制会让新公开主页在演示包中缺样式。
保持原脚本的子路径重写、ES模块复制、只读接口与资源约束，相关公共测试由 A 更新。

公开静态演示的老资料仅有 education 时，显示做任务书同样的保守映射；不生成学生认证。

## 4 资料与头像流程

- 资料页并行读取新资料与原信誉/商品/收藏/订单接口，账号、Token、页面代次和hash一致时才渲染/写 state.me。
- 保留订单、收藏、我发布的、公开主页、信誉记录/申诉、退出、试用改密、管理员/客服入口。
- 学院只读且没有 name，不被提交到新接口；资料POST只包含任务书白名单和资料版本。
- 保存时两个用户表单统一锁定，防止资料/头像同时提交旧版本；退出和导航仍可使用。
- 失败留在原表单，显示可读错误；409不更新版本、不重试、不丢输入。
- “查看服务器资料并核对”只展示新版。采用该版本保留本地输入须明确点击，仍需再次保存；服务器再次变化仍可409。
- “重新载入/用服务器资料替换”需要确认，明确替换输入；不顺手删除其他领域草稿或服务器记录。
- 文件选择先本地预览；“上传并预览”调用专用上传接口，再以捕获的Bearer请求读取私有WebP。
- 读取私有媒体仅接受服务端的 `/media/ua_<32hex>` 固定路径，禁止重定向和缓存；所有JSON仍通过既有api。
- 上传成功只打开确认按钮，不自动公开；确认/移除走同一资料版本，成功只更新资料摘要与版本，不丢未保存的文本。
- 默认头像在图像下方；加载错误隐藏img并恢复默认说明，不使用内联onerror。

core/http.js 当前只抛出 message。本领域用固定的 `资料已更新，请重新载入并核对` 识别自有409合同，
也支持 A 在 Error 上增补 status=409。A 可加 status 以便其他领域通用使用，但不改现有错误JSON或调用方式。
页面没有自行创建第二套 fetch JSON 封装或会话状态。

## 5 运行验证与截图由 A 执行

模块测试源码：`tests/user_profile.test.mjs`，使用能按项目方式加载原生ES模块的 Node 环境。
浏览器测试源码：`tests/user_center_browser_smoke.py`，默认拒绝运行，需要 A 明确提供 --run：

```powershell
python tests/user_center_browser_smoke.py --run --output artifacts/user-center
```

需要指定自己的 Chromium 时追加 `--chromium 完整浏览器路径`；脚本不下载依赖或代选不安全启动参数。
仅在 A 接线完成且授权创建合成临时数据的环境执行，不能在 B 本机执行。

浏览器脚本使用真实HTTP和临时账号，检查选项保存回填、转义、公开响应无敏感字段、真实409、
匿名读取未选头像403/已选头像200/移除后403、伪PNG上传失败、晚到成功响应不能覆盖换号后的账户、
四档宽度和工作人员入口。延迟响应场景先让旧请求真实提交成功，再延后交付响应并等待旧操作结束。

截图输出：me/profile 的375、390、768、1440宽度，移动端409对照和上传失败。
这些是预定输出名，B未运行脚本，当前没有截图，不附旧截图冒充。

还需 A 人工/现有套件补充：从真实注册UI到登录、键盘Tab/Enter与读屏标签、弱网/持续等待、
旧小程序保存兼容、真实旧数据受控副本、实际备份恢复和窗口缩放后的主按钮可见性。
默认头像、长昵称/长简介、缺资料、商品跳转及他人主页私聊均应复核。

## 6 交接状态

本页所列公共文件 B 未修改。若未接新资料路由，mine() 会明确报告资料服务响应错误，
不会用旧接口伪装新功能已接通；A应一次完成后端接线、动作/事件注册、CSS和导出复制。
代码具备供 A 接入的结构，实际可用性与验收通过须由 A/用户运行后记录。
