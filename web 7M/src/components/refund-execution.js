import { e } from '../core/dom.js';
import { date, money } from '../core/format.js';

export function refundExecutionPanel(ticket) {
  const execution=ticket.refund_execution;
  if (!execution) return '';
  const states={not_started:'尚未执行模拟退款',failed:'执行失败：原退款事务已回滚，请管理员核对后重试',
    succeeded:'已模拟退款成功',legacy_recorded:'历史流水已记录，未补造执行时间'};
  const approval={pending:'审核尚未结案',approved:'已同意退款并完成模拟执行',closed_without_refund:'工单已结案，未批准退款'};
  const reconciled=execution.ledger_consistent===true?'核对一致':execution.ledger_consistent===false?'流水异常，请管理员核查':'尚无执行成功记录';
  return `<section class="notice refund-execution" data-refund-execution aria-label="模拟退款执行记录"><h3>模拟退款进度</h3><p>审核：${e(approval[execution.approval_status]||'待核实')}</p><p>执行：${e(states[execution.state]||'执行结果待核实')}</p><p>流水：${reconciled}</p>${execution.amount_cents!=null?`<p>本次记录金额：¥${money(execution.amount_cents)}</p>`:''}${execution.attempts?`<p>已记录执行尝试：${Number(execution.attempts)} 次</p>`:''}${execution.executed_at?`<small>模拟执行时间：${date(execution.executed_at)}</small>`:''}<small>当前全部为模拟；不代表微信退款或实际银行到账。</small></section>`;
}
