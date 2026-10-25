import { isRecord } from '@/shared/http/client.js';

const STREAM_PATH = '/api/ai/chat/stream';
const MAX_EVENT_CHARS = 64 * 1024;
const MAX_STREAM_BYTES = 1024 * 1024;
const MAX_ANSWER_CHARS = 20000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** @typedef {{token: string, epoch: number}} PetSession 仅在认证边界读取的旧会话。 */
/** @typedef {{role: 'user'|'assistant', content: string}} PetHistory 已完整结束的历史消息。 */
/** @typedef {{question: string, history: PetHistory[], client_turn_id: string}} PetQuestion 本轮明确提交的问题。 */
/** @typedef {Record<string, unknown> & {answer: string, action: string}} PetAnswer 保留旧 AI DTO 的已检查回答。 */
/** @typedef {{signal?: AbortSignal, onDelta?: (text: string, delta: string) => void, isCurrent?: () => boolean}} PetStreamOptions 页面取消、增量显示与轮次守卫。 */

export class PetStreamError extends Error {
  /** 保留已生成文本，让页面明确显示中断，禁止自动补发收费请求。 @param {string} message 展示文案。 @param {string} code 错误类别。 @param {number} [status] HTTP 状态。 @param {string} [partial] 已接收的回答。 */
  constructor(message, code, status = 0, partial = '') {
    super(message);
    this.name = 'PetStreamError';
    this.code = code;
    this.status = status;
    this.partial = partial;
    this.incomplete = true;
    this.aborted = code === 'ABORTED' || code === 'STALE_RESPONSE';
  }
}

/** 输入采用白名单，避免额外地址、系统角色和隐藏凭据进入请求。 @param {unknown} value 待发送的数据。 @returns {PetQuestion} 独立复制的最小请求。 */
function decodeQuestion(value) {
  if (
    !isRecord(value) ||
    Object.keys(value).some((key) => !['question', 'history', 'client_turn_id'].includes(key)) ||
    typeof value.question !== 'string' ||
    !value.question.trim() ||
    [...value.question].length > 300 ||
    typeof value.client_turn_id !== 'string' ||
    !UUID.test(value.client_turn_id) ||
    !Array.isArray(value.history) ||
    value.history.length > 4
  ) {
    throw new PetStreamError('问题、历史或轮次格式不正确', 'INVALID_INPUT');
  }
  const history = value.history.map((item) => {
    if (
      !isRecord(item) ||
      Object.keys(item).some((key) => !['role', 'content'].includes(key)) ||
      !['user', 'assistant'].includes(String(item.role)) ||
      typeof item.content !== 'string' ||
      !item.content.trim() ||
      [...item.content].length > MAX_ANSWER_CHARS
    ) {
      throw new PetStreamError('历史消息格式不正确', 'INVALID_INPUT');
    }
    return { role: /** @type {PetHistory['role']} */ (item.role), content: item.content };
  });
  return { question: value.question, history, client_turn_id: value.client_turn_id };
}

/** 对旧 DTO 的呈现必需字段进行检查，其他已有字段原样兼容。 @param {unknown} value done 携带的旧 AI DTO。 @returns {PetAnswer} 纯文本回答与旧元数据。 */
function decodeAnswer(value) {
  if (
    !isRecord(value) ||
    typeof value.answer !== 'string' ||
    !value.answer.trim() ||
    value.answer.length > MAX_ANSWER_CHARS ||
    typeof value.action !== 'string'
  ) {
    throw new PetStreamError('完整回答格式不正确', 'INVALID_EVENT');
  }
  for (const key of ['sources', 'links', 'products', 'orders', 'suggestions']) {
    if (key in value && !Array.isArray(value[key]))
      throw new PetStreamError('回答附加资料格式不正确', 'INVALID_EVENT');
  }
  return /** @type {PetAnswer} */ (value);
}

/** 建立有界 SSE 行解析器，跨块保留 UTF-8 与 CRLF，空行才提交事件。 @param {(event: string, data: string) => void} dispatch 命名事件处理器。 */
function createEventParser(dispatch) {
  let buffer = '';
  let name = '';
  /** @type {string[]} 当前帧的多行 data。 */
  let data = [];
  let eventSize = 0;
  /** 接收已完整的一行；注释与 id/retry 不触发业务状态。 @param {string} value 不含换行符的行。 */
  function line(value) {
    if (!value) {
      if (data.length) dispatch(name || 'message', data.join('\n'));
      name = '';
      data = [];
      eventSize = 0;
      return;
    }
    eventSize += value.length;
    if (eventSize > MAX_EVENT_CHARS) throw new PetStreamError('流式事件过长', 'STREAM_LIMIT');
    if (value.startsWith(':')) return;
    const colon = value.indexOf(':');
    const field = colon < 0 ? value : value.slice(0, colon);
    let content = colon < 0 ? '' : value.slice(colon + 1);
    if (content.startsWith(' ')) content = content.slice(1);
    if (field === 'event') name = content;
    if (field === 'data') data.push(content);
  }
  /** 增量处理网络文本，块尾 CR 留给下个块以兼容 CRLF。 @param {string} text 本块解码文本。 @param {boolean} [eof] 是否已结束网络。 */
  function push(text, eof = false) {
    buffer += text;
    let start = 0;
    for (let index = 0; index < buffer.length; index++) {
      const character = buffer[index];
      if (character !== '\r' && character !== '\n') continue;
      if (character === '\r' && index === buffer.length - 1 && !eof) break;
      line(buffer.slice(start, index));
      if (character === '\r' && buffer[index + 1] === '\n') index++;
      start = index + 1;
    }
    buffer = buffer.slice(start);
    if (buffer.length + eventSize > MAX_EVENT_CHARS)
      throw new PetStreamError('流式事件过长', 'STREAM_LIMIT');
    // SSE 未由空行结束的最后一帧不能当作 done，连接关闭不代表生成成功。
  }
  return { push };
}

/** 为宠物唯一同源入口显式注入旧 Bearer，不接受组件提供外部 URL。 @param {{fetcher?: typeof fetch, readSession: () => PetSession, expire: () => void}} dependencies 可隔离测试的网络与会话边界。 */
export function createPetStreamClient({ fetcher = fetch, readSession, expire }) {
  /** 每次操作仅发送一次 POST；只有匹配本轮的 done 才能完成。 @param {PetQuestion} value 原问题、至多四条完整历史与 UUID。 @param {PetStreamOptions} [options] 取消与增量回调。 @returns {Promise<PetAnswer>} 旧 AI DTO。 */
  async function answer(value, options = {}) {
    const input = decodeQuestion(value);
    const identity = { ...readSession() };
    if (!identity.token) throw new PetStreamError('请先登录后与小转交流', 'UNAUTHORIZED', 401);
    const controller = new AbortController();
    /** @type {ReadableStreamDefaultReader<Uint8Array>|undefined} 当前网络 reader。 */
    let reader;
    let partial = '';
    let status = 0;
    let turned = false;
    /** @type {PetAnswer|undefined} 仅 done 可以赋值。 */
    let result;
    /** 取消底层流和请求，读取中断无需等待供应商继续输出。 */
    function abort() {
      controller.abort();
      void reader?.cancel().catch(() => undefined);
    }
    /** 账号 epoch 与页面轮次都要仍有效；迟到响应不得污染新账号。 */
    function ensureCurrent() {
      const current = readSession();
      if (
        current.token !== identity.token ||
        current.epoch !== identity.epoch ||
        options.isCurrent?.() === false
      )
        throw new PetStreamError('请求所属上下文已失效', 'STALE_RESPONSE');
      if (options.signal?.aborted || controller.signal.aborted)
        throw new PetStreamError('本次生成已停止', 'ABORTED');
    }
    /** 解码单一业务帧；error 与 done 是终态，delta 始终使用纯文本。 @param {string} event 命名 SSE 事件。 @param {string} text 合并后的 data 字段。 */
    function dispatch(event, text) {
      ensureCurrent();
      if (result) return;
      /** @type {unknown} 外部事件对象。 */
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        throw new PetStreamError('流式事件不是有效 JSON', 'INVALID_EVENT');
      }
      if (!isRecord(data)) throw new PetStreamError('流式事件格式不正确', 'INVALID_EVENT');
      if (event === 'error') {
        if (
          typeof data.code !== 'string' ||
          !data.code ||
          typeof data.message !== 'string' ||
          !data.message
        )
          throw new PetStreamError('流式错误格式不正确', 'INVALID_EVENT');
        throw new PetStreamError(data.message, data.code, status);
      }
      if (event === 'turn') {
        if (turned || data.client_turn_id !== input.client_turn_id)
          throw new PetStreamError('回答轮次不匹配', 'INVALID_EVENT');
        turned = true;
        return;
      }
      if (!turned) throw new PetStreamError('流式回答缺少轮次确认', 'INVALID_EVENT');
      if (event === 'delta') {
        if (typeof data.text !== 'string')
          throw new PetStreamError('回答增量格式不正确', 'INVALID_EVENT');
        partial += data.text;
        if (partial.length > MAX_ANSWER_CHARS)
          throw new PetStreamError('回答内容过长', 'STREAM_LIMIT');
        if (data.text) options.onDelta?.(partial, data.text);
        return;
      }
      if (event === 'done') {
        if (data.client_turn_id !== input.client_turn_id)
          throw new PetStreamError('回答轮次不匹配', 'INVALID_EVENT');
        result = decodeAnswer(data.result);
        return;
      }
      throw new PetStreamError('流式事件类型不正确', 'INVALID_EVENT');
    }
    options.signal?.addEventListener('abort', abort, { once: true });
    try {
      ensureCurrent();
      const response = await fetcher(STREAM_PATH, {
        method: 'POST',
        credentials: 'same-origin',
        redirect: 'error',
        signal: controller.signal,
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${identity.token}`,
        },
        body: JSON.stringify(input),
      });
      status = response.status;
      if (response.body) reader = response.body.getReader();
      ensureCurrent();
      const mime = (response.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
      if (!response.ok) {
        // 只检查有界 JSON 错误，代理 HTML、5xx 与迟到错误不能退出当前账号。
        let code = 'HTTP_ERROR';
        let message = '服务暂时不可用，当前输入和已生成内容会保留';
        if (status === 401 && (mime === 'application/json' || mime.endsWith('+json')) && reader) {
          const decoder = new globalThis.TextDecoder('utf-8', { fatal: true });
          let body = '';
          while (body.length <= MAX_EVENT_CHARS) {
            const chunk = await reader.read();
            ensureCurrent();
            if (chunk.done) {
              body += decoder.decode();
              break;
            }
            body += decoder.decode(chunk.value, { stream: true });
          }
          if (body.length <= MAX_EVENT_CHARS) {
            try {
              const error = JSON.parse(body);
              if (
                isRecord(error) &&
                ((['UNAUTHORIZED', 'UNAUTHENTICATED', 'SESSION_EXPIRED'].includes(
                  String(error.code),
                ) &&
                  typeof error.message === 'string' &&
                  error.message) ||
                  (typeof error.error === 'string' && error.error))
              ) {
                ensureCurrent();
                expire();
                code = 'UNAUTHORIZED';
                message = '会话已失效，请重新登录';
              }
            } catch {
              /* 损坏 JSON 仍属于普通 HTTP 错误，不改变会话。 */
            }
          }
        }
        throw new PetStreamError(message, code, status);
      }
      if (mime !== 'text/event-stream' || !reader)
        throw new PetStreamError('服务未返回流式回答', 'INVALID_RESPONSE', status);
      const decoder = new globalThis.TextDecoder('utf-8', { fatal: true });
      const parser = createEventParser(dispatch);
      let received = 0;
      while (!result) {
        const chunk = await reader.read();
        ensureCurrent();
        if (chunk.done) {
          parser.push(decoder.decode(), true);
          break;
        }
        received += chunk.value.byteLength;
        if (received > MAX_STREAM_BYTES)
          throw new PetStreamError('流式响应过长', 'STREAM_LIMIT', status);
        parser.push(decoder.decode(chunk.value, { stream: true }));
      }
      ensureCurrent();
      if (!result)
        throw new PetStreamError('回答中途断开，已生成内容尚未完成', 'INCOMPLETE_STREAM', status);
      return result;
    } catch (error) {
      let failure =
        error instanceof PetStreamError
          ? error
          : new PetStreamError('连接中断，已生成内容尚未完成', 'NETWORK_ERROR', status);
      // 清会话本身会递增 epoch；明确认证错误仍保留 UNAUTHORIZED 分类。
      if (failure.code !== 'UNAUTHORIZED') {
        try {
          ensureCurrent();
        } catch (currentError) {
          if (currentError instanceof PetStreamError) failure = currentError;
        }
      }
      failure.partial = partial;
      failure.status = status || failure.status;
      throw failure;
    } finally {
      options.signal?.removeEventListener('abort', abort);
      if (reader) {
        try {
          await reader.cancel();
        } catch {
          /* 断网或已取消时不掩盖原错误。 */
        }
        reader.releaseLock();
      }
      controller.abort();
    }
  }
  return { answer };
}
