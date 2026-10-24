import { describe, expect, it, vi } from 'vitest';
import { createLegacyClient } from './client.js';

describe('旧业务协议兼容边界', () => {
  /** 旧数组响应保持数组类型，并通过同源请求携带当前会话。 */
  it('保留旧数组和数字编号，不伪造 v1 封套', async () => {
    const fetcher = vi.fn(
      /** @type {typeof fetch} */ (
        async () => new Response('[{"id":7}]', { headers: { 'content-type': 'application/json' } })
      ),
    );
    const client = createLegacyClient({ fetcher, token: () => 'session', expire: vi.fn() });
    expect(await client('/products')).toEqual([{ id: 7 }]);
    expect(fetcher.mock.calls[0][0]).toBe('/api/products');
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe(
      'Bearer session',
    );
  });
  /** 代理 HTML 或服务端错误不能删除登录态；写入超时明确标记结果未知。 */
  it('500 保留会话且标记未知写入结果', async () => {
    const expire = vi.fn();
    const client = createLegacyClient({
      token: () => 's',
      expire,
      fetcher: async () => new Response('<html>bad</html>', { status: 502 }),
    });
    await expect(client('/checkout', { body: { key: 'original' } })).rejects.toMatchObject({
      outcomeUnknown: true,
      status: 502,
    });
    expect(expire).not.toHaveBeenCalled();
  });
  /** 页面挂起期间切换账号，旧响应必须失效，避免内容写入新账号页面。 */
  it('拒绝账号切换后的迟到响应和第三方路径', async () => {
    let token = 'a';
    const client = createLegacyClient({
      token: () => token,
      expire: vi.fn(),
      fetcher: async () => {
        token = 'b';
        return Response.json({ id: 1 });
      },
    });
    await expect(client('/me')).rejects.toMatchObject({ name: 'AbortError' });
    await expect(client('//third.party/secret')).rejects.toThrow();
  });
});
