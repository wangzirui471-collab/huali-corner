# GitHub Python 项目参考核查

日期：2026-10-15。用途：为转角的统一数据、接口和代码规范选择参考，不表示已经接入这些项目。

## 读取方法与限制

GitHub 搜索和仓库 REST API 经当前网络代理返回 `403 Forbidden`，因此未完成校园二手项目的全站搜索或排名比较。原生 HTTPS Git 可以读取公开仓库；本次对下列已知项目执行了浅克隆，读取对应提交的 README、许可证和部分源码。

未运行上游项目，未安装其依赖，未把第三方实现复制进转角，也未使用账号令牌。不能根据仓库可读推断上游代码已经过安全审计或适用于转角全部业务。

## 已核查项目

| 项目 | 本次读取的提交 | 许可证 | 可参考内容 |
| --- | --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | `db04f5b7ed05e3408be73d2c62ae04653be3b3fb` | MIT，读取根目录LICENSE | Python类型模型、请求校验、响应模型、OpenAPI接口文档 |
| [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) | `7257e606cb94eada1dca40173e2b7f99dd549bc6` | MIT，读取根目录LICENSE | 公开模型与内部模型分离、登录路由、权限依赖、测试及配置组织 |
| [Django REST Framework](https://github.com/encode/django-rest-framework) | `14998d0a735f8ed6abd86751fd6984a9277a1d40` | BSD三条款，读取LICENSE.md | 序列化与数据层分离、权限、列表分页等设计参考 |
| [Ruff](https://github.com/astral-sh/ruff) | `829455624d78f2e89669e4b4b14af2b96abdb1ae` | MIT；LICENSE另含第三方声明 | Python格式化、静态检查和导入排序 |

许可证描述以本次读取的具体提交为依据。若后续复制代码，应记录来源路径、提交、修改，并保留该文件适用的版权、许可证及相关第三方声明；不能把本表当作所有子目录、素材和依赖的许可证明。

## 兼容性发现

- 本次FastAPI与DRF主项目声明Python至少3.10。
- 全栈模板的 `backend/pyproject.toml` 要求 `>=3.14,<4.0`，使用数据库、邮件等一整套依赖，不能直接放进用户现有Python3.8环境。
- 当前转角固定的Pillow12.3.0元数据要求Python至少3.10；旧Python中的路径兼容修复不能等同于整套依赖兼容。
- 统一方案建议开发和部署使用Python3.12，实施时实际解析并固定兼容依赖版本。参考模板的架构，不复制其运行环境或整套依赖。

## 选型结论

建议使用FastAPI与请求/响应模型组织新的接口层，Ruff统一Python风格，保留转角已有模拟交易、权限及备份逻辑。继续使用SQLite试点，不因参考全栈模板而强行引入PostgreSQL、邮件服务、JWT、React或Docker。

不得用模板的邮箱密码恢复替换当前未验证手机号的安全恢复流程，也不得把模板普通CRUD当作支付托管、退款仲裁或500人分群的完整实现。

相关资料：[统一Python数据与接口方案](../superpowers/specs/2026-10-15-python-api-standardization-design.md)。
