# Cloudflare 部署授权准备

当前目标是把完整可登录试用版放到用户自己的 Cloudflare 账户。GitHub 代码仓库授权不包含 Cloudflare 授权。

## 安全配置

1. 注册 / 登录 Cloudflare 控制台，确认用于本项目的账户。
2. 在本任务的环境设置中填写非秘密变量 `CLOUDFLARE_ACCOUNT_ID`。
3. 在环境设置的秘密项填写 `CLOUDFLARE_API_TOKEN`，不要把 Token、密码或恢复码发到聊天或提交 GitHub。
4. Token 限定到该账户的必要 Workers Scripts、D1、Workers R2 Storage 编辑权限。若初始化需要其他权限，按明确错误最小增加；不要提供 Global API Key。
5. 应用网络设置中登记的 Cloudflare API、文档和试用网址域名。保存配置草稿本身不会立即让当前运行环境获得授权或联网能力。

R2 或其他服务如果要求绑定付款方式，请先在平台核对计划与费用。本次没有授权自动启用付费计划。

若你无法使用当前环境的秘密设置，可以保留 Token 不分享，在自己的电脑用 Wrangler 的浏览器登录方式授权；后续由经过审阅的部署文件完成发布。

## 当前检查结果

- 开发环境的 Wrangler 4.151.1 已安装并可运行。
- `wrangler whoami` 返回未登录；没有可用的 Cloudflare 账号授权。
- 当前环境访问 `api.cloudflare.com` 和 `developers.cloudflare.com` 被代理 403 拦截。域名需求已保存到配置草稿，等待实际应用后复测。
- 现有虚构数据的只读资源包通过 Workers 静态资源 `deploy --dry-run`，未上传、未生成网址，也没有 D1/R2 绑定。
- 只读资源通过不等于完整 Python 后端可以发布。实际迁移范围见 [Cloudflare 试用版迁移设计](superpowers/specs/2026-10-17-cloudflare-trial-design.md)。

当前没有创建或修改任何 Cloudflare 网站、Worker、数据库、存储桶、DNS 或账单设置。
