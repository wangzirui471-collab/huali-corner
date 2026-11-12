# 当前网页版 Vue 3 框架接入与验证

## 版本与实现

基线 `a36cead19ba6ce5548a6fb6d8e6ed8a748da2e8d`；独立工作区 `huali-corner-current-web-20261112`，分支 `refactor/vue3-current-web-20261112`。保留此前上线的登录/超时/AI 草稿修复。

新增 Vue 3.5.45、Vue Router 4.6.4、Pinia 3.0.4、Vite 8.3.8、plugin-vue 6.0.10，项目锁文件管理，未安装全局依赖或复制 node_modules。Vue App / RouterView / 稳定 LegacyPage 管理生命周期；原页面、事件和权限继续执行。旧 state 与 Pinia 指向同一实例，运行句柄 shallowRef，不复制账号或购物车。

旧 hash 分享链接兼容；新导航使用官方 hash history。Vue watch 是切页唯一渲染来源，同页重载继续调用原 render。原 renderId / token 过期响应保护、账号分离和 AI 跨页单例保留。监听委托可释放，取消未开始的预热，应用卸载增加 epoch。

Vite 只编译入口和 JS；原 CSS 按原顺序透传，图片及办公/宠物静态资源按原地址与字节复制。旧 CSS 的浏览器容错不被 PostCSS 改写。小程序添加独立 CommonJS 作用域，避免父 package.json 的 ESM 标记影响原 require。

Worker 仅修改静态资源目录到 `web 7M/dist`；后端 Python、AI 服务、交易 writer、真实绑定、TLS 和密码 KDF 未改。公开演示导出改用临时 `base=./` 编译结果，仍只创建临时合成数据且拒绝覆盖非空输出。

## 已实际执行

- 重构前登录 8 场景、AI 四屏宽原基线均通过。
- `npm test --prefix "web 7M"`：生产构建与全部 **16 个脚本通过**；框架合同 **6 项通过**，原模块/商品流/轮播/缓存/会话/宠物/用户中心/小程序合同保留。
- `tests/vue_static_assets.test.cjs`：**153 个原公开资源字节一致**、样式链接顺序一致，产物不含 package、配置、依赖和未编译入口。
- 登录浏览器：390/1440 下 HTML401 保留会话、JSON401 正常过期；登录/注册 HTML 响应保留输入且无原始 JSON 错误。共 8 场景。
- AI 浏览器：360/390/768/1440，客服/办公/工作三模式就地切换、失败输入恢复、不覆盖新草稿、不自动重发、窗口边界/放大还原/60–160% 缩放；脚本错误为 0。
- 原网页对照：390/1440 下各 14 个普通/权限页面的 HTML、关键布局及样式一致；额外所有者用户工作台与带查询参数的管理员工作台各两屏检查。另检查旧链接、历史前后、同页刷新、Pinia、AI 草稿跨页、未知路由、慢商品响应与卸载事件释放。
- `python -m unittest discover -s tests -p test_public_demo.py`：**3 项通过**，包含只读导出和源图片保护。
- `tests/vue_public_demo_browser_smoke.cjs`：390/1440 从 `/demo/` 子目录打开，编译入口和轮播图片成功，原只读功能保留，无真实 API、页面脚本错误为 0。

完整浏览器最后一轮的执行结果以本机 `artifacts/vue3-refactor-20261112/final-browser.log` 及 `framework-browser-result.json` 为准；不能将仅失败分支诊断运行的空 comparisons 当成完整验收。

## 审查与限制

已请独立只读审查者检查框架、路由和构建接线，发现两处 hash 替换错误（排序函数、商品失败卡片）和原演示仍复制未编译源码的问题。均先复现后修复；排序单测和商品失败浏览器断言保留。公开演示另验子目录资源，不能仅靠文件列表测试判断能运行。

保留的一项轻微限制：整应用卸载/HMR 时，body 上旧 AI 单例的定时器、观察器及部分监听仍存活；普通路由切换本来应保留 AI。未将这次框架接入扩为 AI 实现重写。

本机 Node 24.18、Edge 无头浏览器、全合成接口与临时演示数据。没有真实账号/模型/数据库写、生产发布、微信真机验收。源码与构建测试不能代替 Worker 运行验收。
