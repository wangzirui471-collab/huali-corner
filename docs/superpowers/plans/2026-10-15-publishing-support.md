# 转角简化发布与售后 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 实际交付简化发布、账号草稿、专用客服、退货后重售与有依据的信誉处理，保留已有试用数据。

**Architecture:** 沿用Python/SQLite与现有HTTP合同。把草稿与发布生命周期放入publishing.py，客服人员与信誉规则放入operations.py；网页发布页单独模块化，小程序使用同一后端。

**Tech Stack:** 现有Python、SQLite、Pillow、原生JavaScript、微信小程序；不迁移FastAPI，不新增付费服务。

**Spec:** docs/转角软件需求文档-v1.1.md，第7.0/7.5/10.4—10.6/12节。

## Global Constraints

- 用户明确要求开始实现上一批；订单推送、系统通知权限和新增/自定义地址留到下一批。
- 当前仍是模拟支付、退款和结算；不生成真实默认客服密码或伪装身份认证。
- 三张不同角度实拍图继续必需；未知字段不默认完好。
- 信誉0—100，低于60禁止新发布/重新上架；处罚必须有已核实工单、权限和申诉。
- 保留数据目录、账号密码摘要、订单快照、原账务与既有隐私/并发保护。
- 在现有feat/huali-pilot分支执行；不创建额外工作树，不修改/workspace/-。

## Review Focus

- 保存与发布超时重试不得复制商品；用数据库事务与固定草稿ID验证。
- 多窗口旧版本和另一账号不得覆盖或读取草稿；版本冲突必须可恢复。
- 退货未收到、仅退款或已重售后不得重复上架同一实物。
- 客服不能自行成为管理员、审批自己交易或绕过退款与信誉授权。
- 刷新/关窗的恢复必须包括已上传照片；未上传完或本机存储失败需明确提示。

### Task 1: Python草稿与安全发布

**Files:** Modify db.py、market.py、server.py；Create publishing.py、tests/test_publishing.py。
**Interfaces:** save_draft(user_id, payload)、get_draft(user_id, draft_id)、list_drafts(user_id)、delete_draft(user_id, draft_id)、publish_draft(user_id, draft_id, version)、relist_draft(user_id, product_id)。

- [x] 写失败测试：不完整草稿持久化、跨账号隔离、版本冲突、图片归属、失败保留、发布幂等、低分限制。
- [x] 运行unittest定位缺少方法，确认RED。
- [x] 以增量表/列迁移实现草稿；发布与关闭草稿同事务；保留直接发布旧接口。
- [x] 运行草稿与原有完整Python测试，确认GREEN并提交。

### Task 2: 客服账号、退货重售与信誉

**Files:** Modify db.py、market.py、auth.py、server.py、manage_trial.py；Create operations.py、tests/test_operations.py。
**Interfaces:** create_support(admin_id,payload)、set_support_active(admin_id,user_id,is_active)、return_action(user_id,ticket_id,action)、apply_penalty(admin_id,target_user_id,ticket_id,rule_key,reason)、reverse_penalty(admin_id,audit_id,appeal_ticket_id,reason)、recover_credit(admin_id,target_user_id,ticket_id,reason)。

- [x] 写失败测试：独立客服登录/停用、普通人越权、客服退款审批限制、退货收到前后重售、同实物已重售拒绝、首次警告/重复扣分/申诉冲回。
- [x] 确认RED后实现人员账号与工单状态，退款方式和退回确认，基于规则的信誉记录。
- [x] 原订单和图片快照保留，退回后创建预填草稿而非自动在售。
- [x] 运行完整Python测试，核对支付账务、库存并发、恢复后账号；提交。

### Task 3: 网页简化发布与恢复

**Files:** Create web/publishing.js、web/publishing.css；Modify web/app.js、web/index.html、scripts/build_public_demo.py；Create tests/publishing_browser_smoke.py。
**Interfaces:** window.ZJPublisher.render(dependencies,draft_id)、submit(form)、drafts(dependencies)、suspend()、clearLocal(user_id)。

- [x] 写真实浏览器失败场景：一页点选、关闭重载恢复文字与三图、发布重试、类别切换、无权限/冲突提示。
- [x] 写失败验证后实现2秒防抖、账号本地补偿、图片即时上传、草稿箱及明确保存状态。
- [x] 网页旧上传分支委托新模块；保持账号切换保护与静态只读演示。
- [x] 运行浏览器流程与现有试用/响应式测试，修正真实回归并提交。

### Task 4: 客服售后与信誉操作界面、小程序适配

**Files:** Modify web/app.js、miniprogram/pages/publish/index.js及wxml、miniprogram/pages/hub/index.js及wxml；Add native publishing regression test。
**Interfaces:** 复用Task1/2的API；小程序只提交草稿/动作，不自行决定库存、退款和信誉。

- [x] 写失败验证：专用客服管理、认领/建议与管理员审批、退回/收到确认、重上架、信誉规则与申诉可操作。
- [x] 实现网页完整入口及小程序草稿保存/恢复和售后操作；不要求微信后台推送权限。
- [x] 验证界面权限和服务端权限一致；小程序工具/真机结果不冒充已执行。
- [x] 完整测试通过后提交。

### Task 5: 交付与整体审查

**Files:** Update README.md、docs/TRIAL.md、docs/PROGRESS.md、需求核对表及试用交付ZIP。

- [x] 更新用户可操作说明、支持账号建立和处罚政策说明。
- [x] 执行Python全套、客户端单元验证、真实双账号浏览器与静态导出检查。
- [x] 根据整体代码审查修复重要问题，再验证；明确Windows和微信真机未执行项。
- [x] 打包不含数据库、个人信息和默认凭证的源码，记录真实交付状态。
