import { describe, expect, it } from 'vitest';
import { createCheckoutAttempt, yuanToCents, orderActions } from './checkout.js';

describe('交易前端合同', () => {
  /** 小数金额不经过浮点乘法截断，非法值不能发送到后端。 */
  it('以整数分转换金额并拒绝第三位小数', () => {
    expect(yuanToCents('19.90')).toBe(1990);
    expect(yuanToCents('0')).toBe(0);
    expect(() => yuanToCents('0.001')).toThrow();
    expect(() => yuanToCents('-1')).toThrow();
  });
  /** 结果未知时保留原始请求身份，异内容不能借用原幂等键。 */
  it('同内容沿用键，异内容必须先处理未确认结果', () => {
    const attempt = createCheckoutAttempt();
    const body = {
      product_ids: [2, 1],
      delivery: 'pickup',
      address: '图书馆',
      appointment: 1900000000,
    };
    const first = attempt.prepare(8, body);
    expect(attempt.prepare(8, { ...body, product_ids: [1, 2] }).key).toBe(first.key);
    expect(() => attempt.prepare(8, { ...body, address: '操场' })).toThrow();
    attempt.clear();
    expect(attempt.prepare(8, body).key).not.toBe(first.key);
  });
  /** 仅合法订单参与人显示动作；按钮只是引导，最终权限由服务端检查。 */
  it('按订单状态与买卖双方区分动作', () => {
    expect(orderActions({ buyer_id: 1, seller_id: 2, status: 'paid' }, 2)).toContain('deliver');
    expect(orderActions({ buyer_id: 1, seller_id: 2, status: 'paid' }, 3)).toEqual([]);
    expect(orderActions({ buyer_id: 1, seller_id: 2, status: 'awaiting_payment' }, 1)).toContain(
      'pay',
    );
  });
});
