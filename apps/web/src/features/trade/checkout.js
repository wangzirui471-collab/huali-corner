/** @typedef {{product_ids: number[], delivery: string, address: string, appointment: number, want_id?: number}} CheckoutBody 旧下单参数。 */
/** 将元字符串精确转为整数分；拒绝负数、科学计数和超出既有上限的金额。 @param {string} value 元。 */
export function yuanToCents(value) {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) throw new Error('金额最多两位小数');
  const [whole, fraction = ''] = value.trim().split('.');
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  if (!Number.isSafeInteger(cents) || cents > 1_000_000)
    throw new Error('金额应在 0 至 10000 元之间');
  return cents;
}
/**
 * 维护未确认请求的不可变快照；由页面按账号保存到会话草稿。
 * @param {{fingerprint: string, key: string}|null} [initial] 上次未确认的请求。
 */
export function createCheckoutAttempt(initial = null) {
  let pending = initial;
  return {
    /** 同内容沿用原键，异内容须先确认旧结果，不能默默生成第二张单。 @param {number} buyer 买家。 @param {CheckoutBody} body 请求。 */
    prepare(buyer, body) {
      const product_ids = [...body.product_ids].sort((a, b) => a - b);
      const fingerprint = JSON.stringify({
        buyer,
        product_ids,
        delivery: body.delivery,
        address: body.address,
        appointment: body.appointment,
        want_id: body.want_id || null,
      });
      if (pending && pending.fingerprint !== fingerprint)
        throw new Error('上一笔提交结果未确认，请先查看订单并按原内容恢复。');
      pending ||= { fingerprint, key: crypto.randomUUID() };
      return { ...body, product_ids, key: pending.key };
    },
    /** 成功或服务端明确拒绝后清除；网络失败和 5xx 不调用。 */
    clear() {
      pending = null;
    },
    /** 返回可按账号暂存的幂等身份，不包含密码。 */
    snapshot() {
      return pending;
    },
  };
}
/**
 * 从旧订单状态推导展示动作，最终归属、竞态和权限由原服务端检查。
 * @param {{buyer_id: number, seller_id: number, status: string, schedule_confirmed?: boolean}} order 订单。
 * @param {number} actor 当前用户编号。
 */
export function orderActions(order, actor) {
  const buyer = order.buyer_id === actor;
  if (!buyer && order.seller_id !== actor) return [];
  const actions = [];
  if (order.status === 'awaiting_payment')
    actions.push(...(buyer ? ['pay', 'cancel', 'edit'] : ['edit']));
  if (order.status === 'paid')
    actions.push(
      ...(buyer
        ? ['cancel']
        : [...(!order.schedule_confirmed ? ['confirm_schedule'] : []), 'deliver']),
    );
  if (buyer && order.status === 'awaiting_handover') actions.push('handover');
  if (buyer && order.status === 'awaiting_receipt') actions.push('receive');
  if (
    buyer &&
    ['paid', 'awaiting_handover', 'awaiting_receipt', 'completed'].includes(order.status)
  )
    actions.push('refund');
  if (['paid', 'awaiting_handover'].includes(order.status)) actions.push('reschedule');
  if (order.status === 'completed') actions.push('review');
  return actions;
}
