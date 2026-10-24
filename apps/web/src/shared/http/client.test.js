/** 合成响应覆盖故障、幂等、凭据与账号切换，不访问任何真实 API。 */
import { describe, expect, it, vi } from 'vitest';
import { ApiError, createHttpClient } from './client';
import { decodeHealth } from './health';
import { RequestScope, StaleResponseError } from './request-scope';

/**
 * 构造服务端同形封套，避免测试直接跳过 HTTP 数据边界。
 * @param {string} [code] 合成错误码。
 * @param {unknown} [data] 合成业务数据。
 */
function envelope(
  code = 'OK',
  data = { status: 'ok', environment: 'test', business_ready: false },
) {
  return {
    code,
    message: '合成结果',
    data,
    error: null,
    request_id: 'synthetic-request',
    meta: { schema_version: 'v1', simulation: true },
  };
}

describe('v1 HTTP 协议', () => {
  /** 兼容入口已配置和全站已迁移是不同事实，解码时不丢失这两个标记。 */
  it('区分兼容入口配置与完整业务就绪', () => {
    expect(
      decodeHealth({
        status: 'ok',
        environment: 'test',
        business_ready: false,
        compat_enabled: true,
      }).compat_enabled,
    ).toBe(true);
    expect(() =>
      decodeHealth({
        status: 'ok',
        environment: 'test',
        business_ready: false,
        compat_enabled: 'true',
      }),
    ).toThrow();
  });
  /** 正常响应经运行时解码，并且携带同源 Cookie 策略。 */
  it('解码成功数据并携带同源凭据', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(envelope()));
    const client = createHttpClient(fetcher, new RequestScope());
    expect((await client.request('/api/v1/health', decodeHealth)).environment).toBe('test');
    expect(fetcher.mock.calls[0]?.[1]?.credentials).toBe('same-origin');
  });

  /** 500 和 HTML 错误不会被解释为成功数据或身份失效。 */
  it('保留服务器失败与未知写入结果', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('<html>proxy</html>', { status: 502 }));
    const client = createHttpClient(fetcher, new RequestScope());
    await expect(
      client.request('/api/v1/orders', decodeHealth, { method: 'POST' }),
    ).rejects.toMatchObject({
      status: 502,
      code: 'INVALID_RESPONSE',
      outcomeUnknown: true,
    });
  });

  /** 限流保留服务端重试时间，并区分请求明确失败与提交结果未知。 */
  it('保留 Retry-After 和稳定错误码', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      Response.json(envelope('RATE_LIMITED', null), {
        status: 429,
        headers: { 'Retry-After': '30' },
      }),
    );
    const client = createHttpClient(fetcher, new RequestScope());
    await expect(client.request('/api/v1/health', decodeHealth)).rejects.toMatchObject({
      retryAfter: '30',
      status: 429,
      code: 'RATE_LIMITED',
    });
  });

  /** 网络中断不证明写入失败，客户端需带原幂等键恢复操作。 */
  it('断网后保留原幂等键及未知结果标记', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('offline'));
    const client = createHttpClient(fetcher, new RequestScope());
    await expect(
      client.request('/api/v1/orders', decodeHealth, {
        method: 'POST',
        idempotencyKey: 'same-operation',
        csrfToken: 'synthetic-csrf',
      }),
    ).rejects.toBeInstanceOf(ApiError);
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get('Idempotency-Key')).toBe('same-operation');
    expect(headers.get('X-CSRF-Token')).toBe('synthetic-csrf');
  });

  /** 服务端即使忽略取消信号，旧身份的迟到响应也不得交给新页面。 */
  it('切换账号后拒绝迟到响应', async () => {
    /** @type {(value: Response) => void} 手动控制合成响应的完成时间。 */
    let resolveResponse = () => undefined;
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveResponse = resolve;
        }),
    );
    const scope = new RequestScope();
    const client = createHttpClient(fetcher, scope);
    const result = client.request('/api/v1/health', decodeHealth);
    scope.reset();
    resolveResponse(Response.json(envelope()));
    await expect(result).rejects.toBeInstanceOf(StaleResponseError);
  });

  /** TS 类型无法约束真实网络数据，错误 DTO 必须显式拒绝。 */
  it('拒绝旧封套和不符合 DTO 的数据', async () => {
    for (const body of [[1, 2], envelope('OK', { status: 'wrong' })]) {
      const fetcher = vi.fn().mockResolvedValue(Response.json(body));
      const client = createHttpClient(fetcher, new RequestScope());
      await expect(client.request('/api/v1/health', decodeHealth)).rejects.toBeInstanceOf(ApiError);
    }
  });
});
