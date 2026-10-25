import { effectScope, nextTick } from 'vue';
import { afterEach, expect, it, vi } from 'vitest';
import { session } from '@/shared/legacy/session.js';
import { usePetChat } from './use-pet-chat.js';

/** 测试后撤销账号，确保账号内存不串例。 */
afterEach(() => {
  session.token = '';
  session.me = null;
  session.epoch++;
});

/** 断流部分答案不能成为已完成历史，也不能清掉原输入或自动重试。 */
it('未知失败保留输入，partial不进历史，显式重试沿用原轮次', async () => {
  session.token = 'synthetic';
  const answer = vi.fn().mockImplementation(async (_input, options) => {
    options.onDelta('部分回答');
    throw new Error('连接中断');
  });
  const scope = effectScope();
  const chat = scope.run(() => usePetChat({ answer }));
  if (!chat) throw new Error('未创建状态');
  chat.state.question = '交付怎么约？';
  await chat.submit();
  expect(chat.state.question).toBe('交付怎么约？');
  expect(chat.state.messages).toHaveLength(0);
  expect(chat.state.partial).toBe('部分回答');
  expect(answer).toHaveBeenCalledTimes(1);
  await chat.submit();
  expect(answer.mock.calls[1][0].client_turn_id).toBe(answer.mock.calls[0][0].client_turn_id);
  scope.stop();
});

/** 忽略取消的服务端迟到delta和done也不得泄露给新账号。 */
it('切换账号取消请求并丢弃迟到回答与输入', async () => {
  session.token = 'old';
  let finish = /** @type {(value: Record<string, unknown>) => void} */ (() => undefined);
  let delta = /** @type {(value: string) => void} */ (() => undefined);
  let signal = /** @type {AbortSignal|null} */ (null);
  const answer = vi.fn().mockImplementation((_input, options) => {
    signal = options.signal;
    delta = options.onDelta;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  const scope = effectScope();
  const chat = scope.run(() => usePetChat({ answer }));
  if (!chat) throw new Error('未创建状态');
  chat.state.question = '旧问题';
  const pending = chat.submit();
  session.token = 'new';
  session.epoch++;
  await nextTick();
  expect(/** @type {AbortSignal|null} */ (signal)?.aborted).toBe(true);
  delta('旧部分');
  finish({ answer: '旧回答' });
  await pending;
  expect(chat.state.question).toBe('');
  expect(chat.state.partial).toBe('');
  expect(chat.state.messages).toEqual([]);
  scope.stop();
});

/** 只有完整回合可以提供上下文，最多最近四条，停止生成保留草稿。 */
it('上下文限于四条完整消息，停止生成保持问题', async () => {
  session.token = 'synthetic';
  const answer = vi.fn().mockResolvedValue({ answer: '完整回答', products: [] });
  const scope = effectScope();
  const chat = scope.run(() => usePetChat({ answer }));
  if (!chat) throw new Error('未创建状态');
  for (const question of ['一', '二', '三', '四']) {
    chat.state.question = question;
    await chat.submit();
  }
  expect(answer.mock.calls[3][0].history).toEqual([
    { role: 'user', content: '二' },
    { role: 'assistant', content: '完整回答' },
    { role: 'user', content: '三' },
    { role: 'assistant', content: '完整回答' },
  ]);
  answer.mockImplementation(() => new Promise(() => {}));
  chat.state.question = '保留问题';
  void chat.submit();
  chat.stop();
  expect(chat.state.busy).toBe(false);
  expect(chat.state.question).toBe('保留问题');
  scope.stop();
});
