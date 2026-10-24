import { expect, it, vi } from 'vitest';
import { createLegacyClient } from './client.js';

/** 仅显式开启时，登录和订单走新 FastAPI；商品等未迁移领域仍使用原 writer。 */
it('按领域切换 FastAPI 兼容入口并解开封套', async () => {
  const fetcher = vi.fn(
    /** @type {typeof fetch} */ (
      async () =>
        Response.json({
          code: 'OK',
          message: '成功',
          data: [{ id: 601, total: 1800 }],
          error: null,
          request_id: 'synthetic',
          meta: { schema_version: 'v1', simulation: true },
        })
    ),
  );
  const client = createLegacyClient({
    fetcher,
    token: () => 'original-token',
    expire: vi.fn(),
    useV1: true,
  });
  expect(await client('/orders')).toEqual([{ id: 601, total: 1800 }]);
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/compat/orders');
  await client('/products');
  expect(fetcher.mock.calls[1][0]).toBe('/api/products');
});

/** 下单原键继续携带到新 API；5xx 保留账号和未知结果，不能换键自动重试。 */
it('新入口保留原下单键与未知结果', async () => {
  const expire = vi.fn();
  const fetcher = vi.fn(
    /** @type {typeof fetch} */ (
      async () =>
        Response.json(
          {
            code: 'LEGACY_UNAVAILABLE',
            message: '请核对原订单',
            data: null,
            error: { fields: [] },
            request_id: 'synthetic',
            meta: { schema_version: 'v1', simulation: true },
          },
          { status: 502 },
        )
    ),
  );
  const client = createLegacyClient({
    fetcher,
    token: () => 'original-token',
    expire,
    useV1: true,
  });
  await expect(client('/checkout', { body: { key: 'same-key' } })).rejects.toMatchObject({
    outcomeUnknown: true,
    message: '请核对原订单',
    requestId: 'synthetic',
  });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Idempotency-Key')).toBe('same-key');
  expect(expire).not.toHaveBeenCalled();
});
