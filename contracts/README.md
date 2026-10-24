# v1 协议与旧接口兼容

`openapi.json` 从 `apps/api` 的实际 FastAPI 模型生成，现包含健康接口和 `/api/v1/compat` 的身份/订单兼容入口；兼容接入不等于底层业务已迁移。

修改服务端模型后，从 `apps/api` 运行 `uv run python scripts/export_contract.py`，再从 `apps/web` 运行 `npm run generate:api`。生成的 JSON 与 `.d.ts` 一同提交，禁止手工修改生成类型；业务代码仍使用 JavaScript。

旧 `/api` 保持数组、数字 ID、金额分和时间秒等原合同。显式 `/api/v1/compat/*` 在封套 data 内同样保留旧 DTO，原 Bearer 和旧唯一 writer 不变。其他规范化新业务使用字符串 ID、整数分、UTC 毫秒和稳定封套，迁移时在领域 mapper 显式转换；不对旧客户端原地改类型。接手与接口表见 [交接说明](../docs/refactor/AI-TAKEOVER-AND-INTEGRATION.md)，决策见 0006。
