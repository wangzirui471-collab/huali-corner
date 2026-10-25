import { ApiError, createHttpClient, isRecord } from '@/shared/http/client.js';

const ANSWER_PATH = '/api/v1/support/assistant/answer';
/** @typedef {{token: string, epoch: number}} AssistantSession 只读取认证所需的旧会话。 */
/** @typedef {{client_turn_id: string, question: string}} AssistantQuestion 一次提问及其固定关联键。 */
/** @typedef {{document_id: string, title: string, version: string, content: string}} AssistantSource 服务端认可的公开资料。 */
/** @typedef {{client_turn_id: string, answer_text: string, mode: 'mock'|'llm'|'handoff', sources: AssistantSource[], handoff: {recommended: boolean, reason: string, next_path: '/support/new'}}} AssistantAnswer 经过领域解码的回答。 */

/**
 * 严格校验 FAQ 资料和固定人工入口，不把模型自报路径作为导航依据。
 * @param {unknown} value HTTP 解封套后的未知数据。
 * @param {string} turnId 仅接受当前轮的回答。
 * @returns {AssistantAnswer} 可按纯文本展示的领域数据。
 */
function decodeAnswer(value, turnId) {
  if (
    !isRecord(value) ||
    value.client_turn_id !== turnId ||
    typeof value.answer_text !== 'string' ||
    !value.answer_text.trim() ||
    !['mock', 'llm', 'handoff'].includes(String(value.mode)) ||
    !Array.isArray(value.sources) ||
    !isRecord(value.handoff) ||
    typeof value.handoff.recommended !== 'boolean' ||
    typeof value.handoff.reason !== 'string' ||
    value.handoff.next_path !== '/support/new'
  )
    throw new TypeError('FAQ 响应合同不正确');
  const sources = value.sources.map((source) => {
    if (
      !isRecord(source) ||
      typeof source.document_id !== 'string' ||
      !source.document_id ||
      typeof source.title !== 'string' ||
      !source.title ||
      typeof source.version !== 'string' ||
      !source.version ||
      typeof source.content !== 'string' ||
      !source.content
    )
      throw new TypeError('FAQ 来源合同不正确');
    return {
      document_id: source.document_id,
      title: source.title,
      version: source.version,
      content: source.content,
    };
  });
  return {
    client_turn_id: turnId,
    answer_text: value.answer_text,
    mode: /** @type {AssistantAnswer['mode']} */ (value.mode),
    sources,
    handoff: {
      recommended: value.handoff.recommended,
      reason: value.handoff.reason,
      next_path: '/support/new',
    },
  };
}

/**
 * 为唯一 FAQ 入口注入原 Bearer；不扩大通用 HTTP 客户端的认证范围。
 * @param {{fetcher: typeof fetch, scope: import('@/shared/http/request-scope.js').RequestScope, readSession: () => AssistantSession, expire: () => void}} dependencies 网络、取消和身份依赖。
 */
export function createAssistantApi({ fetcher, scope, readSession, expire }) {
  /**
   * 一次显式请求只发送问题与轮次，不自动重试模型调用。
   * @param {AssistantQuestion} question 原问题和 UUID。
   * @returns {Promise<AssistantAnswer>} 校验后的回答。
   */
  async function answer(question) {
    const identity = readSession();
    if (!identity.token) throw new ApiError('请先登录后使用规则问答', 'UNAUTHORIZED', 401);
    /**
     * 仅向固定同源入口发送凭据，禁止组件和模型供应商接触会话拼装。
     * @type {typeof fetch}
     */
    const authenticatedFetch = async (input, options) => {
      if (input !== ANSWER_PATH) throw new TypeError('只允许 FAQ 同源入口');
      const headers = new Headers(options?.headers);
      headers.set('Authorization', `Bearer ${identity.token}`);
      return fetcher(input, { ...options, headers, redirect: 'error' });
    };
    const http = createHttpClient(authenticatedFetch, scope);
    try {
      return await http.request(
        ANSWER_PATH,
        (value) => decodeAnswer(value, question.client_turn_id),
        {
          method: 'POST',
          body: { client_turn_id: question.client_turn_id, question: question.question },
        },
      );
    } catch (error) {
      const current = readSession();
      // HTML 代理响应不构成明确身份判定，迟到的旧身份失败也不得清除新会话。
      if (
        error instanceof ApiError &&
        error.status === 401 &&
        error.code !== 'INVALID_RESPONSE' &&
        current.token === identity.token &&
        current.epoch === identity.epoch
      )
        expire();
      throw error;
    }
  }
  return { answer };
}
