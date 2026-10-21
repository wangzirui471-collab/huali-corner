# v1 协议与旧接口兼容

`openapi.json` 从 `apps/api` 的实际 FastAPI 模型生成，当前仅包含健康接口；不能把骨架合同当作登录、商品或交易已迁移。

修改服务端模型后，从 `apps/api` 运行 `uv run python scripts/export_contract.py`，再从 `apps/web` 运行 `npm run generate:api`。生成的 JSON 与 `.d.ts` 一同提交，禁止手工修改生成类型；业务代码仍使用 JavaScript。

旧 `/api` 保持数组、数字 ID、金额分和时间秒等原合同。新业务切片使用 `/api/v1` 的字符串 ID、整数分、明确时间单位和稳定封套，迁移时在领域 mapper 显式转换；不对旧客户端原地改类型。当前骨架没有挂载业务适配器，也没有新的业务写入口。
