import { onScopeDispose, reactive, watch } from 'vue';
import { ApiError } from '@/shared/http/client.js';
import { RequestScope, StaleResponseError } from '@/shared/http/request-scope.js';
import { clearSession, session } from '@/shared/legacy/session.js';
import { createAssistantApi } from './api.js';

/** 管理单次公开规则问答；只保存在页面内存，账号切换与卸载清空并取消网络。 */
export function useAssistant() {
  const scope = new RequestScope();
  const state = reactive({
    question: '',
    busy: false,
    error: '',
    forbidden: false,
    answer: /** @type {import('./api.js').AssistantAnswer|null} */ (null),
    turn: /** @type {import('./api.js').AssistantQuestion|null} */ (null),
  });
  const api = createAssistantApi({
    fetcher: (...args) => fetch(...args),
    scope,
    readSession: () => ({ token: session.token, epoch: session.epoch }),
    expire: clearSession,
  });
  /** 内容修改即终止旧轮次；失败期间不修改输入便保留原 UUID 供显式重试。 */
  function invalidateTurn() {
    scope.reset();
    state.turn = null;
    state.answer = null;
    state.busy = false;
    state.error = '';
    state.forbidden = false;
  }
  /** 身份切换和页面卸载不得保留任何前账号问题或回答。 */
  function clear() {
    invalidateTurn();
    state.question = '';
  }
  watch(() => state.question, invalidateTurn, { flush: 'sync' });
  watch(() => [session.token, session.epoch, session.me?.id], clear, { flush: 'sync' });
  onScopeDispose(clear);

  /** 显式提问或重试；不自动重试，失败保留原问题与轮次，禁止并发付费请求。 */
  async function submit() {
    if (state.busy) return;
    if (!state.question.trim() || Array.from(state.question).length > 800) {
      state.error = '请输入 1—800 字的问题';
      return;
    }
    if (!session.token) {
      state.error = '请先登录后使用规则问答';
      return;
    }
    const turn = state.turn ?? { client_turn_id: crypto.randomUUID(), question: state.question };
    state.turn = turn;
    state.error = '';
    state.forbidden = false;
    state.answer = null;
    state.busy = true;
    const epoch = scope.epoch;
    try {
      const answer = await api.answer(turn);
      if (epoch !== scope.epoch) return;
      state.answer = answer;
      // 同一问题成功后仍沿用原轮次，重复点击不会再次请求付费生成。
    } catch (error) {
      if (epoch !== scope.epoch || error instanceof StaleResponseError) return;
      state.forbidden = error instanceof ApiError && error.status === 403;
      state.error = error instanceof Error ? error.message : '问答暂时不可用，请稍后重试';
    } finally {
      if (epoch === scope.epoch) state.busy = false;
    }
  }
  return { state, submit };
}
