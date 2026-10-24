import { ApiError, isRecord } from '../http/client.js';

/** 只切换已经实现的身份/订单操作，其他旧业务仍保留原路由与数据合同。 */
const COMPAT_PATHS = new Set([
  'GET /auth/salt',
  'POST /auth/login',
  'POST /auth/logout',
  'GET /me',
  'GET /orders',
  'GET /order',
  'POST /checkout',
  'POST /order/action',
  'POST /order/update',
  'POST /order/change',
]);

/** @typedef {{body?: unknown, signal?: AbortSignal}} LegacyOptions 旧接口请求选项。 */
/**
 * 同源旧协议适配器：保留旧 DTO；不将未装配业务的新 v1 健康接口当作业务 API。
 * @param {{fetcher?: typeof fetch, token: () => string, expire: () => void, useV1?: boolean}} dependencies 会话与网络边界。
 */
export function createLegacyClient({
  fetcher = fetch,
  token,
  expire,
  useV1 = import.meta.env.VITE_HUALI_COMPAT_API === '1',
}) {
  /**
   * 只允许 /api 下的相对业务路径；账号变化后丢弃迟到响应。
   * @param {string} path 例如 /products，不接受绝对地址。
   * @param {LegacyOptions} [options] 写入 JSON 或取消信号。
   * @returns {Promise<unknown>} 旧 JSON 在领域 mapper 继续校验。
   */
  return async function request(path, options = {}) {
    if (!/^\/[a-z][a-z0-9/-]*(?:\?[^#]*)?$/i.test(path) || path.includes('\\')) {
      throw new Error('业务接口路径无效');
    }
    const session = token();
    const writing = options.body !== undefined;
    const compat = useV1 && COMPAT_PATHS.has(`${writing ? 'POST' : 'GET'} ${path.split('?')[0]}`);
    const headers = new Headers({ Accept: 'application/json' });
    if (session) headers.set('Authorization', `Bearer ${session}`);
    if (writing) headers.set('Content-Type', 'application/json');
    if (
      compat &&
      path === '/checkout' &&
      isRecord(options.body) &&
      typeof options.body.key === 'string'
    )
      headers.set('Idempotency-Key', options.body.key);
    let response;
    try {
      response = await fetcher(`${compat ? '/api/v1/compat' : '/api'}${path}`, {
        method: writing ? 'POST' : 'GET',
        headers,
        body: writing ? JSON.stringify(options.body) : undefined,
        signal: options.signal,
        credentials: 'same-origin',
        redirect: 'error',
      });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      throw new ApiError(
        writing ? '网络中断，提交结果尚未确认；请保留原请求重试。' : '连接失败，请稍后重试。',
        'NETWORK_ERROR',
        0,
        undefined,
        undefined,
        writing,
      );
    }
    let body;
    if (/application\/json|\+json/i.test(response.headers.get('content-type') || '')) {
      try {
        body = await response.json();
      } catch {
        /* 协议错误由下面的统一边界处理。 */
      }
    }
    if (session !== token()) throw new DOMException('账号已切换', 'AbortError');
    if (response.status === 401 && session) expire();
    const envelope =
      compat &&
      isRecord(body) &&
      typeof body.code === 'string' &&
      typeof body.message === 'string' &&
      typeof body.request_id === 'string' &&
      'data' in body &&
      'error' in body &&
      isRecord(body.meta) &&
      body.meta.schema_version === 'v1' &&
      body.meta.simulation === true
        ? body
        : null;
    if (compat) body = envelope?.data;
    if (
      !response.ok ||
      (compat && (!envelope || envelope.code !== 'OK')) ||
      body === undefined ||
      body === null ||
      typeof body !== 'object'
    ) {
      const message =
        envelope && typeof envelope.message === 'string'
          ? envelope.message
          : isRecord(body) && typeof body.error === 'string'
            ? body.error
            : '服务暂时不可用；当前输入会保留。';
      throw new ApiError(
        message,
        envelope && typeof envelope.code === 'string'
          ? envelope.code
          : response.status === 401
            ? 'UNAUTHENTICATED'
            : 'LEGACY_REQUEST_FAILED',
        response.status,
        envelope && typeof envelope.request_id === 'string' ? envelope.request_id : undefined,
        response.headers.get('Retry-After') || undefined,
        writing && (response.status >= 500 || response.ok),
      );
    }
    return body;
  };
}
