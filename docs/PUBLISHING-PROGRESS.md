# Execution ledger — plan: docs/superpowers/plans/2026-10-15-publishing-support.md

User authorization: 开始实现上一批功能，订单推送和地址放后面。
Ruling: 在现有Python HTTP合同和feat/huali-pilot中实现，不采用未获同意的FastAPI/Python运行版本迁移；保留旧接口与数据。若日后统一v1接口，需额外适配成本。
Pre-flight: Task1草稿的fields/version与Task3网页和Task4小程序共享；原始表单金额以元字符串存草稿，Python发布时转整数分；直接旧publish仍以分为单位。
Pre-flight: Task2退货确认与Task1重新上架共享stock_key；只有收到实物且模拟退款结束才可重售。
Pre-flight: Task2的客服仅受理/建议，管理员审批退款与信誉；网页/小程序必须与服务端一致。
Task 1: complete — 8 domain draft tests and HTTP draft test RED→GREEN; full Python suite63/63 passed. Drafts are account-owned, CAS-versioned, retained30 days, publishing is transactional/idempotent; existing database gains only additive columns/tables.
Task 2: complete —10 operations and2 HTTP tests RED→GREEN; complete Python suite75/75 passed. Dedicated support is independently provisioned/disabled, refund approval is admin-only, return receipt gates refund/relisting, stock lineage prevents double resale, penalties/appeal reversals/recovery are evidence-linked and audited.

Task 3: complete — real Chromium draft close/reopen, photo recovery after failed cloud save, failed photo replacement warning, stale closed-window conflict/copy and account-switch isolation passed. Publishing is one page with conditional book options and optional detail section.
Task 4: complete — web independent support management, queue/filter/assignment, private evidence, return/refund/relist, credit/reverse/recover forms; native drafts, evidence, return/refund recommendation and resale/appeal entry points adapted. Advanced personnel/credit approvals remain in web workbench; no WeChat tool/device build claimed.
Review: five Important issues reproduced and fixed with regressions: historical stock ancestor resale, arbitrary legacy credit bypass, review/recommendation assignment theft, out-of-order native photo uploads and reopening stale dirty caches. Independent targeted recheck found no remaining Important issue.
Verification:80 Python tests;5 Node scripts; real draft/support/trial/legacy Chromium flows passed. Windows compatibility tests simulate environment limitations on Linux/Python3.12; native Windows/WeChat execution remains unrun.
Ruling: remote main gained user commitddfdf90 (additional directories and runtime artifacts). Preserve it; publish this feature on feat/huali-pilot without forcing/replacing main. Release package explicitly excludes databases, uploads, backups, bytecode, credentials, user spreadsheet and duplicate legacy source directories.
Task 5: complete — clean 68-file source ZIP extracted and run; old-release password accounts, photos and paid order migrated in a temporary data directory and remained valid; new drafts/support worked. Responsive375/390/768/1440, static subpath/no-write browser and simulated Windows MIME regression passed. Actual Windows/WeChat/public deployment remains unrun. Publish only feature branch, preserving main.
