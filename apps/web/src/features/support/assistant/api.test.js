import { expect, it, vi } from 'vitest';
import { createAssistantApi } from './api.js';
import { RequestScope, StaleResponseError } from '@/shared/http/request-scope.js';

export const TURN = '11111111-1111-4111-8111-111111111111';
/** 构造公开 FAQ 合同，所有资料均为合成数据。 */
export function answer() {
  return {
    client_turn_id: TURN,
    answer_text: '请先与卖家协商交付时间。',
    mode: 'mock',
    sources: [{ document_id: 'faq-1', title: '交付说明', version: 'demo', content: '双方确认。' }],
    handoff: { recommended: false, reason: '', next_path: '/support/new' },
  };
}
/** 构造实际 HTTP 封套，避免绕过运行时校验。 @param {unknown} data 领域数据。 @param {string} [code] 错误码。 */
export function envelope(data, code = 'OK') {
  return {
    code,
    message: '合成响应',
    data,
    error: null,
    request_id: 'faq-test',
    meta: { schema_version: 'v1', simulation: true },
  };
}
/** 创建隔离客户端并暴露会话失效观察点。 @param {typeof fetch} fetcher 合成网络。 @param {RequestScope} [scope] 取消作用域。 */
function client(fetcher, scope = new RequestScope()) {
  const expire = vi.fn();
  const api = createAssistantApi({
    fetcher,
    scope,
    readSession: () => ({ token: 'test-bearer', epoch: 1 }),
    expire,
  });
  return { api, expire };
}
/** 提问只传固定 UUID 和原问题；认证在边界显式注入且保持同源。 */
it('固定同源路径显式携带 Bearer 并校验公开 FAQ 合同', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(envelope(answer())));
  const { api } = client(fetcher);
  expect(await api.answer({ client_turn_id: TURN, question: '怎样交付？' })).toEqual(answer());
  const [path, options] = fetcher.mock.calls[0];
  expect(path).toBe('/api/v1/support/assistant/answer');
  expect(new Headers(options.headers).get('Authorization')).toBe('Bearer test-bearer');
  expect(options.credentials).toBe('same-origin');
  expect(options.redirect).toBe('error');
  expect(JSON.parse(options.body)).toEqual({ client_turn_id: TURN, question: '怎样交付？' });
});
/** 拒绝错轮回答、伪造来源字段及可跳向外站的转人工路径。 */
it('拒绝不完整来源、错轮 UUID 与非固定转人工路径', async () => {
  for (const data of [
    { ...answer(), client_turn_id: '22222222-2222-4222-8222-222222222222' },
    { ...answer(), sources: [{ document_id: 'fake', title: '缺少正文', version: 'v1' }] },
    {
      ...answer(),
      handoff: { recommended: true, reason: '转人工', next_path: 'https://evil.test' },
    },
    { ...answer(), mode: 'unknown' },
  ]) {
    const { api } = client(vi.fn().mockResolvedValue(Response.json(envelope(data))));
    await expect(
      api.answer({ client_turn_id: TURN, question: '怎样交付？' }),
    ).rejects.toMatchObject({ code: 'INVALID_DATA' });
  }
});
/** 无凭据时不发送网络请求，不能暗中依赖尚未落地的 Cookie 身份。 */
it('无会话时拒绝请求', async () => {
  const fetcher = vi.fn();
  const api = createAssistantApi({
    fetcher,
    scope: new RequestScope(),
    readSession: () => ({ token: '', epoch: 0 }),
    expire: vi.fn(),
  });
  await expect(api.answer({ client_turn_id: TURN, question: '规则？' })).rejects.toMatchObject({
    status: 401,
  });
  expect(fetcher).not.toHaveBeenCalled();
});
/** 代理 HTML 或身份服务故障不等于账号失效；只有有效封套的 401 才清会话。 */
it('502、503 和 HTML 401 不清会话，明确 401 才清会话', async () => {
  for (const status of [502, 503, 401]) {
    const { api, expire } = client(
      vi.fn().mockResolvedValue(new Response('<html>upstream</html>', { status })),
    );
    await expect(api.answer({ client_turn_id: TURN, question: '规则？' })).rejects.toBeDefined();
    expect(expire).not.toHaveBeenCalled();
  }
  const { api, expire } = client(
    vi.fn().mockResolvedValue(Response.json(envelope(null, 'UNAUTHORIZED'), { status: 401 })),
  );
  await expect(api.answer({ client_turn_id: TURN, question: '规则？' })).rejects.toMatchObject({
    status: 401,
  });
  expect(expire).toHaveBeenCalledOnce();
});
/** 即使网络忽略取消，也不展示旧账号回答或用迟到 401 清新会话。 */
it('作用域重置后丢弃迟到成功与迟到 401', async () => {
  for (const status of [200, 401]) {
    /** @type {(value: Response) => void} 控制网络返回时间。 */
    let finish = () => undefined;
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const scope = new RequestScope();
    const { api, expire } = client(fetcher, scope);
    const pending = api.answer({ client_turn_id: TURN, question: '规则？' });
    const signal = fetcher.mock.calls[0][1].signal;
    scope.reset();
    expect(signal.aborted).toBe(true);
    finish(
      Response.json(
        envelope(status === 200 ? answer() : null, status === 200 ? 'OK' : 'UNAUTHORIZED'),
        { status },
      ),
    );
    await expect(pending).rejects.toBeInstanceOf(StaleResponseError);
    expect(expire).not.toHaveBeenCalled();
  }
});
