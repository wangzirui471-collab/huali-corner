import { expect, it, vi } from 'vitest';
import { createPetStreamClient } from './stream-client.js';

const TURN = '11111111-1111-4111-8111-111111111111';
const INPUT = { question: '怎样交付？', history: [], client_turn_id: TURN };
const RESULT = { answer: '请先协商。', action: 'none', sources: [], products: [], mode: 'llm' };
/** 构造真实 SSE 帧；空行明确表示事件边界。 @param {string} name 事件名。 @param {unknown} data 事件数据。 */
function frame(name, data) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}
/** 构造完整轮次；调用方可替换增量。 @param {string} [delta] 中文增量。 */
function complete(delta = '请先协商。') {
  return (
    frame('turn', { client_turn_id: TURN }) +
    frame('delta', { text: delta }) +
    frame('done', { client_turn_id: TURN, result: RESULT })
  );
}
/** 将编码后的帧按任意字节切片，让测试真实经过 UTF-8 解码器。 @param {string} value 合成 SSE。 @param {number} [size] 每块字节数。 */
function response(value, size = 7) {
  const bytes = new TextEncoder().encode(value);
  return new Response(
    new globalThis.ReadableStream({
      /** 以跨汉字的字节边界送出合成网络块。 @param {ReadableStreamDefaultController<Uint8Array>} controller 可读流。 */
      start(controller) {
        for (let offset = 0; offset < bytes.length; offset += size)
          controller.enqueue(bytes.slice(offset, offset + size));
        controller.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  );
}
/** 创建独立账号与客户端；所有凭据均为合成值。 @param {typeof fetch} fetcher 网络边界。 */
function client(fetcher) {
  const identity = { token: 'synthetic-bearer', epoch: 1 };
  const expire = vi.fn();
  return {
    api: createPetStreamClient({ fetcher, readSession: () => identity, expire }),
    identity,
    expire,
  };
}

/** 中文跨块仍实时回调；只传固定问答字段，凭据只能进入请求头。 */
it('POST 固定同源路径并按 UTF-8 字节增量显示，done 返回旧 AI DTO', async () => {
  const fetcher = vi.fn().mockResolvedValue(response(complete()));
  const { api } = client(fetcher);
  const onDelta = vi.fn();
  expect(await api.answer(INPUT, { onDelta })).toEqual(RESULT);
  expect(onDelta).toHaveBeenCalledExactlyOnceWith('请先协商。', '请先协商。');
  const [path, options] = fetcher.mock.calls[0];
  expect(path).toBe('/api/ai/chat/stream');
  expect(options).toMatchObject({ method: 'POST', credentials: 'same-origin', redirect: 'error' });
  expect(new Headers(options.headers).get('Authorization')).toBe('Bearer synthetic-bearer');
  expect(new Headers(options.headers).get('Accept')).toBe('text/event-stream');
  expect(JSON.parse(options.body)).toEqual(INPUT);
});
/** SSE 注释、CRLF、多行 data 与跨块 CR 均遵守标准帧边界。 */
it('解析 CRLF、注释及多行 JSON data', async () => {
  const source =
    ': heartbeat\r\n\r\n' +
    frame('turn', { client_turn_id: TURN }).replaceAll('\n', '\r\n') +
    'event: delta\r\ndata: {\r\ndata: "text":"你好"}\r\n\r\n' +
    frame('done', { client_turn_id: TURN, result: RESULT });
  const { api } = client(vi.fn().mockResolvedValue(response(source, 1)));
  const onDelta = vi.fn();
  expect(await api.answer(INPUT, { onDelta })).toEqual(RESULT);
  expect(onDelta).toHaveBeenCalledWith('你好', '你好');
});
/** 在连接仍打开且 done 尚未发出时显示增量，防止退化为完整 JSON 后打字。 */
it('服务端尚未完成时立即交付增量并继续累积下一块', async () => {
  /** @type {ReadableStreamDefaultController<Uint8Array>|undefined} 独立推进服务器网络流。 */
  let sink;
  /** @type {() => void} 首次增量到达信号。 */
  let delivered = () => undefined;
  const firstDelta = new Promise((resolve) => {
    delivered = () => resolve(undefined);
  });
  const stream = new globalThis.ReadableStream({
    /** 保持连接打开，测试主动控制后续数据。 @param {ReadableStreamDefaultController<Uint8Array>} controller 合成服务端。 */
    start(controller) {
      sink = controller;
    },
  });
  const { api } = client(
    vi
      .fn()
      .mockResolvedValue(
        new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }),
      ),
  );
  if (!sink) throw new Error('合成网络流未初始化');
  /** @type {string[]} 观察每次真实增量到达后的累计文本。 */
  const received = [];
  let completed = false;
  const pending = api.answer(INPUT, {
    onDelta: (text) => {
      received.push(text);
      delivered();
    },
  });
  void pending.then(() => {
    completed = true;
  });
  sink.enqueue(
    new TextEncoder().encode(
      frame('turn', { client_turn_id: TURN }) + frame('delta', { text: '请先' }),
    ),
  );
  await firstDelta;
  expect(received).toEqual(['请先']);
  expect(completed).toBe(false);
  sink.enqueue(
    new TextEncoder().encode(
      frame('delta', { text: '协商。' }) + frame('done', { client_turn_id: TURN, result: RESULT }),
    ),
  );
  sink.close();
  expect(await pending).toEqual(RESULT);
  expect(received).toEqual(['请先', '请先协商。']);
});
/** 没有 done 的断线与服务端明确失败都保留部分文本；每次只调用一次网络。 */
it('断线和 error 标记未完成且从不自动重试', async () => {
  for (const suffix of [
    '',
    frame('error', { code: 'UPSTREAM_UNAVAILABLE', message: '生成中断' }),
  ]) {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        response(
          frame('turn', { client_turn_id: TURN }) + frame('delta', { text: '已有部分' }) + suffix,
        ),
      );
    const { api } = client(fetcher);
    await expect(api.answer(INPUT)).rejects.toMatchObject({
      partial: '已有部分',
      incomplete: true,
      code: suffix ? 'UPSTREAM_UNAVAILABLE' : 'INCOMPLETE_STREAM',
    });
    expect(fetcher).toHaveBeenCalledOnce();
  }
});
/** 错轮、非 JSON、缺少首帧及超长帧均不能构成成功。 */
it('拒绝错轮、损坏事件、缺失 turn 和超大帧', async () => {
  for (const source of [
    frame('turn', { client_turn_id: 'other' }) + complete(),
    'event: turn\ndata: broken\n\n',
    frame('delta', { text: '先到' }) + complete(),
    frame('turn', { client_turn_id: TURN }) + frame('delta', { text: '字'.repeat(70000) }),
    frame('turn', { client_turn_id: TURN }) +
      frame('done', { client_turn_id: TURN, result: { action: 'none' } }),
  ]) {
    const { api } = client(vi.fn().mockResolvedValue(response(source, 10000)));
    await expect(api.answer(INPUT)).rejects.toMatchObject({ incomplete: true });
  }
});
/** 输入约束在发送前完成；拒绝附加地址或把令牌伪装成上下文。 */
it('发送前拒绝无效问题、历史、UUID 及额外字段', async () => {
  const fetcher = vi.fn();
  const { api } = client(fetcher);
  for (const input of [
    { ...INPUT, question: '字'.repeat(301) },
    { ...INPUT, question: ' ' },
    { ...INPUT, client_turn_id: 'bad' },
    { ...INPUT, history: Array(5).fill({ role: 'user', content: '问题' }) },
    { ...INPUT, history: [{ role: 'system', content: '伪造' }] },
    { ...INPUT, token: 'hidden' },
    { ...INPUT, url: 'https://outside.test' },
  ]) {
    await expect(api.answer(input)).rejects.toMatchObject({ code: 'INVALID_INPUT' });
  }
  expect(fetcher).not.toHaveBeenCalled();
});
/** HTML 401 与普通故障不清会话；明确认证 JSON 401 才能清理。 */
it('区分 MIME 与 HTTP 错误且只对明确有效 401 清会话', async () => {
  for (const status of [200, 401, 502, 503]) {
    const { api, expire } = client(
      vi.fn().mockResolvedValue(
        new Response('<html>代理错误</html>', {
          status,
          headers: { 'Content-Type': 'text/html' },
        }),
      ),
    );
    await expect(api.answer(INPUT)).rejects.toMatchObject({
      code: status === 200 ? 'INVALID_RESPONSE' : 'HTTP_ERROR',
      status,
    });
    expect(expire).not.toHaveBeenCalled();
  }
  const { api, expire } = client(
    vi
      .fn()
      .mockResolvedValue(
        Response.json({ code: 'UNAUTHORIZED', message: '会话失效' }, { status: 401 }),
      ),
  );
  await expect(api.answer(INPUT)).rejects.toMatchObject({ code: 'UNAUTHORIZED', status: 401 });
  expect(expire).toHaveBeenCalledOnce();
});
/** 显式取消会取消 reader 与底层请求；已显示片段仍标为未完成。 */
it('停止生成立即取消 reader 和请求，不再等待网络关闭', async () => {
  const cancel = vi.fn();
  const controller = new AbortController();
  const stream = new globalThis.ReadableStream({
    /** 发出部分数据后保持打开，模拟仍在生成的供应商连接。 @param {ReadableStreamDefaultController<Uint8Array>} sink 网络输出。 */
    start(sink) {
      sink.enqueue(
        new TextEncoder().encode(
          frame('turn', { client_turn_id: TURN }) + frame('delta', { text: '部分' }),
        ),
      );
    },
    cancel,
  });
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }));
  const { api } = client(fetcher);
  const pending = api.answer(INPUT, {
    signal: controller.signal,
    onDelta: () => controller.abort(),
  });
  await expect(pending).rejects.toMatchObject({
    code: 'ABORTED',
    partial: '部分',
    incomplete: true,
  });
  expect(cancel).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
});
/** 账号 epoch 即使复用同一令牌仍失效；迟到 401 无权退出新会话。 */
it('丢弃账号和调用方作用域失效后的迟到结果', async () => {
  for (const status of [200, 401]) {
    /** @type {(value: Response) => void} 推进迟到网络结果。 */
    let finish = () => undefined;
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { api, identity, expire } = client(fetcher);
    const onDelta = vi.fn();
    const pending = api.answer(INPUT, { onDelta });
    identity.epoch++;
    finish(status === 200 ? response(complete()) : Response.json({ error: '请登录' }, { status }));
    await expect(pending).rejects.toMatchObject({ code: 'STALE_RESPONSE' });
    expect(onDelta).not.toHaveBeenCalled();
    expect(expire).not.toHaveBeenCalled();
  }
  const { api } = client(vi.fn().mockResolvedValue(response(complete())));
  await expect(api.answer(INPUT, { isCurrent: () => false })).rejects.toMatchObject({
    code: 'STALE_RESPONSE',
  });
});
