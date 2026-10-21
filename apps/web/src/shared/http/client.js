/** v1 协议客户端；旧 API 保留其原始类型，由独立 mapper 显式迁移。 */

/**
 * @typedef {object} ApiEnvelope 新协议的响应结构，data 在领域边界继续校验。
 * @property {string} code 稳定机器错误码。
 * @property {string} message 安全展示文案。
 * @property {unknown} data 业务数据。
 * @property {unknown} error 字段错误信息。
 * @property {string} request_id 服务端请求编号。
 * @property {{schema_version: 'v1', simulation: true}} meta 协议与模拟交易标记。
 */

export class ApiError extends Error {
  /**
   * 记录安全错误信息；outcomeUnknown 提醒写操作使用原幂等键恢复。
   * @param {string} message 展示文案。
   * @param {string} code 稳定错误码。
   * @param {number} status HTTP 状态，0 表示网络失败。
   * @param {string} [requestId] 服务端请求编号。
   * @param {string} [retryAfter] 服务端建议重试时间。
   * @param {boolean} [outcomeUnknown] 是否无法确认写入结果。
   */
  constructor(message, code, status, requestId, retryAfter, outcomeUnknown = false) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
    this.outcomeUnknown = outcomeUnknown;
  }
}

/**
 * 判断未知外部值是否为对象，不通过断言跳过输入校验。
 * @param {unknown} value 外部数据。
 * @returns {value is Record<string, unknown>} 是否为非数组对象。
 */
export function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * 校验服务端封套结构，排除 HTML 代理错误和旧 API 响应。
 * @param {unknown} value 解码后的网络响应。
 * @returns {value is ApiEnvelope} 是否满足 v1 基础协议。
 */
function isEnvelope(value) {
  return (
    isRecord(value) &&
    typeof value.code === 'string' &&
    typeof value.message === 'string' &&
    typeof value.request_id === 'string' &&
    'data' in value &&
    'error' in value &&
    isRecord(value.meta) &&
    value.meta.schema_version === 'v1' &&
    value.meta.simulation === true
  );
}

/**
 * @typedef {object} RequestOptions 请求选项，不在组件中拼接认证头。
 * @property {'GET'|'POST'|'PATCH'|'DELETE'} [method] 请求方法。
 * @property {unknown} [body] JSON 请求内容。
 * @property {string} [idempotencyKey] 同一次业务重试使用原键。
 * @property {string} [csrfToken] 会话模块提供的防跨站令牌。
 */

/**
 * 注入 fetch 和请求作用域，便于测试断网、取消及响应乱序。
 * @param {typeof fetch} fetcher 网络适配器。
 * @param {import('./request-scope').RequestScope} scope 账号或页面的请求上下文。
 */
export function createHttpClient(fetcher, scope) {
  /**
   * 仅请求同源 v1 路径，decode 将未知数据校验成领域 DTO。
   * @template T
   * @param {string} path 以 /api/v1/ 开始的同源路径。
   * @param {(value: unknown) => T} decode 领域数据校验函数。
   * @param {RequestOptions} [options] 方法、幂等与 CSRF 选项。
   * @returns {Promise<T>} 通过校验的业务数据。
   */
  async function request(path, decode, options = {}) {
    if (!path.startsWith('/api/v1/')) throw new TypeError('仅允许同源 v1 API 路径');
    return scope.run(async (signal) => {
      const method = options.method ?? 'GET';
      const mutation = method !== 'GET';
      const headers = new Headers({ Accept: 'application/json' });
      if (options.body !== undefined) headers.set('Content-Type', 'application/json');
      if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey);
      if (options.csrfToken) headers.set('X-CSRF-Token', options.csrfToken);
      /** @type {Response} 当前网络响应。 */
      let response;
      try {
        response = await fetcher(path, {
          method,
          credentials: 'same-origin',
          signal,
          headers,
          body: options.body === undefined ? undefined : JSON.stringify(options.body),
        });
      } catch {
        throw new ApiError(
          '网络连接中断，请重试',
          'NETWORK_ERROR',
          0,
          undefined,
          undefined,
          mutation,
        );
      }
      /** @type {unknown} 尚未校验的外部响应。 */
      let body;
      try {
        body = await response.json();
      } catch {
        throw new ApiError(
          '服务响应异常，请稍后重试',
          'INVALID_RESPONSE',
          response.status,
          response.headers.get('X-Request-ID') ?? undefined,
          response.headers.get('Retry-After') ?? undefined,
          mutation,
        );
      }
      if (!isEnvelope(body)) {
        throw new ApiError(
          '服务响应格式不正确',
          'INVALID_RESPONSE',
          response.status,
          undefined,
          undefined,
          mutation,
        );
      }
      if (!response.ok || body.code !== 'OK') {
        // 会话处置由 identity 模块根据明确的 401 决定；5xx 不清会话或输入。
        throw new ApiError(
          body.message,
          body.code,
          response.status,
          body.request_id,
          response.headers.get('Retry-After') ?? undefined,
          mutation && response.status >= 500,
        );
      }
      try {
        return decode(body.data);
      } catch {
        throw new ApiError(
          '服务数据格式不正确',
          'INVALID_DATA',
          response.status,
          body.request_id,
          undefined,
          mutation,
        );
      }
    });
  }
  return { request };
}
