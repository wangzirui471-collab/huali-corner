import { onScopeDispose, reactive, watch } from 'vue';
import { clearSession, session } from '@/shared/legacy/session.js';
import { createPetStreamClient } from './stream-client.js';

/** @typedef {{role:'user'|'assistant',content:string,result?:Record<string,unknown>}} PetMessage 完成消息，未完成输出不进入历史。 */
/** @typedef {{question:string,history:{role:'user'|'assistant',content:string}[],client_turn_id:string}} PetQuestion 请求轮次。 */
/** @typedef {{answer:(input:PetQuestion,options:{signal:AbortSignal,onDelta:(text:string)=>void,isCurrent:()=>boolean})=>Promise<Record<string,unknown>>}} ChatClient 流边界。 */
/** 管理账号内存会话；不持久化聊天，不自动重试收费请求。 @param {ChatClient} [client] 可注入受控网络边界。 */
export function usePetChat(
  client = createPetStreamClient({
    readSession: () => ({ token: session.token, epoch: session.epoch }),
    expire: clearSession,
  }),
) {
  const state = reactive({
    question: '',
    busy: false,
    partial: '',
    error: '',
    messages: /** @type {PetMessage[]} */ ([]),
    turn: /** @type {PetQuestion|null} */ (null),
  });
  let generation = 0,
    controller = /** @type {AbortController|null} */ (null);
  /** 停止仅终止当前生成，保留草稿及部分输出并明确标记未完成。 */
  function stop() {
    generation++;
    controller?.abort();
    controller = null;
    if (state.busy) state.error = '已停止生成，当前回答未完成。';
    state.busy = false;
  }
  /** 身份变化和销毁清理所有私密内存，迟到回调由generation再次拦截。 */
  function clear() {
    stop();
    state.question = '';
    state.partial = '';
    state.error = '';
    state.messages = [];
    state.turn = null;
  }
  watch(() => [session.token, session.epoch, session.me?.id], clear, { flush: 'sync' });
  onScopeDispose(clear);
  /** 只在用户提交时发起一轮，未知失败保留原键和问题。 */
  async function submit() {
    if (state.busy) return;
    const question = state.question.trim();
    if (!question || Array.from(question).length > 300) {
      state.error = '请输入 1—300 字的问题';
      return;
    }
    if (!session.token) {
      state.error = '请先登录后与小转聊天';
      return;
    }
    if (!state.turn || state.turn.question !== question)
      state.turn = {
        question,
        client_turn_id: crypto.randomUUID(),
        history: state.messages.slice(-4).map(({ role, content }) => ({
          role,
          content: Array.from(content).slice(0, 300).join(''),
        })),
      };
    const turn = state.turn;
    const current = ++generation;
    controller = new AbortController();
    state.busy = true;
    state.error = '';
    state.partial = '';
    try {
      const result = await client.answer(turn, {
        signal: controller.signal,
        isCurrent: () => current === generation,
        onDelta: (text) => {
          if (current === generation) state.partial = text;
        },
      });
      if (current !== generation) return;
      const content = typeof result.answer === 'string' ? result.answer : '';
      state.messages.push(
        { role: 'user', content: question },
        { role: 'assistant', content, result },
      );
      state.partial = '';
      state.turn = null;
      // 用户在请求过程中编辑的新草稿不能被旧轮次成功清空。
      if (state.question.trim() === question) state.question = '';
    } catch (error) {
      if (current === generation)
        state.error = error instanceof Error ? error.message : '生成未完成，请检查后手动重试。';
    } finally {
      if (current === generation) {
        state.busy = false;
        controller = null;
      }
    }
  }
  return { state, submit, stop, clear };
}
