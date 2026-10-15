# Execution ledger — plan: docs/superpowers/plans/2026-10-15-publishing-support.md

User authorization: 开始实现上一批功能，订单推送和地址放后面。
Ruling: 在现有Python HTTP合同和feat/huali-pilot中实现，不采用未获同意的FastAPI/Python运行版本迁移；保留旧接口与数据。若日后统一v1接口，需额外适配成本。
Pre-flight: Task1草稿的fields/version与Task3网页和Task4小程序共享；原始表单金额以元字符串存草稿，Python发布时转整数分；直接旧publish仍以分为单位。
Pre-flight: Task2退货确认与Task1重新上架共享stock_key；只有收到实物且模拟退款结束才可重售。
Pre-flight: Task2的客服仅受理/建议，管理员审批退款与信誉；网页/小程序必须与服务端一致。
Task 1: complete — 8 domain draft tests and HTTP draft test RED→GREEN; full Python suite63/63 passed. Drafts are account-owned, CAS-versioned, retained30 days, publishing is transactional/idempotent; existing database gains only additive columns/tables.
