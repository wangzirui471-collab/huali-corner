import test from 'node:test';
import assert from 'node:assert/strict';
import { orderProgress } from '../web 7M/src/components/order-progress.js';
import { refundExecutionPanel } from '../web 7M/src/components/refund-execution.js';

test('order progress shows four independent records and escapes server text', () => {
  const progress = Object.fromEntries(['order','delivery','after_sales','funds'].map(key=>[key,{label:`<${key}>`,next_actor:null}]));
  const html = orderProgress({progress});
  for (const label of ['订单进度','交付进度','售后进度','模拟资金']) assert.ok(html.includes(label));
  assert.ok(html.includes('&lt;order&gt;'));
  assert.ok(!html.includes('<order>'));
  assert.equal(orderProgress({}), '');
});

test('refund failure and legacy history never fabricate success or execution time', () => {
  const failed = refundExecutionPanel({refund_execution:{state:'failed',attempts:1,approval_status:'pending',ledger_consistent:null}});
  assert.ok(failed.includes('执行失败'));
  assert.ok(failed.includes('核对后重试'));
  assert.ok(!failed.includes('已模拟退款成功'));
  const legacy = refundExecutionPanel({refund_execution:{state:'legacy_recorded',attempts:0,approval_status:'approved',ledger_consistent:true}});
  assert.ok(legacy.includes('历史流水'));
  assert.ok(legacy.includes('未补造执行时间'));
});
