import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';

globalThis.window = { crypto: webcrypto };
globalThis.sessionStorage = { getItem(){ return null; } };

const { api, prefetch } = await import('../web 7M/src/core/http.js');
const { state } = await import('../web 7M/src/core/state.js');

test('global office response is rejected after account switch', async () => {
  // 全局面板可跨路由等待，但不能把所有者数据交给下一账号。
  state.token = 'owner-before';
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = api('/ai/office', { question: '平台数据概览' }, { global: true });
  state.token = 'user-after';
  finish(Response.json({ answer: '所有者私密数据' }));
  await assert.rejects(pending, /账号已切换/);
});

test('global office response survives route change within the same account', async () => {
  // 保留此前修复的跨页面等待能力，仅豁免页面版本检查。
  state.token = 'same-owner';
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = api('/ai/office', { question: '待处理工单' }, { global: true });
  state.renderId++;
  finish(Response.json({ answer: '本账号结果' }));
  assert.equal((await pending).answer, '本账号结果');
});

test('second first-page list call is served from cache', async () => {
  state.token = '';
  let calls = 0;
  globalThis.fetch = async (url) => {
    calls++;
    assert.equal(url, '/api/products?category=&q=&sort=&limit=40');
    return Response.json([{ id: 1 }]);
  };
  const a = await api('/products?category=&q=&sort=&limit=40');
  const b = await api('/products?category=&q=&sort=&limit=40');
  assert.deepEqual(a, [{ id: 1 }]);
  assert.deepEqual(b, [{ id: 1 }]);
  assert.equal(calls, 1, 'second call must not hit the network');
});

test('cached array is copied so caller sorting cannot corrupt it', async () => {
  state.token = '';
  globalThis.fetch = async () => Response.json([{ id: 2 }, { id: 1 }]);
  const first = await api('/products?t=copy');
  first.sort((x, y) => x.id - y.id);        // 调用方原地排序
  const second = await api('/products?t=copy');
  assert.deepEqual(second.map(x => x.id), [2, 1], 'cache must keep original order');
});

test('paginated posts are never cached', async () => {
  state.token = '';
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json([{ id: calls }]); };
  await api('/posts?limit=20&offset=20');
  await api('/posts?limit=20&offset=20');
  assert.equal(calls, 2, 'offset pages must always refetch');
});

test('a successful write clears the list cache', async () => {
  state.token = '';
  let gets = 0;
  globalThis.fetch = async (url, options) => {
    if (options && options.method === 'POST') return Response.json({ ok: true });
    gets++;
    return Response.json([{ id: 1 }]);
  };
  await api('/products?t=write');
  await api('/products?t=write');                    // cache hit
  await api('/posts', { topic: '交流', body: 'hi' }); // 写操作
  await api('/products?t=write');                    // 必须重新取
  assert.equal(gets, 2);
});

test('cache is isolated per account token', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json([{ id: calls }]); };
  state.token = 'alice';
  const a = await api('/products?t=account');
  state.token = 'bob';
  const b = await api('/products?t=account');
  assert.equal(calls, 2, 'different token must not share cache');
  assert.notDeepEqual(a, b);
});

test('workbench list is cached but polled messages are not', async () => {
  state.token = 'staff';
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json([]); };
  await api('/admin');
  await api('/admin');            // 命中缓存
  assert.equal(calls, 1, 'workbench data should be cached');
  await api('/messages');
  await api('/messages');         // 轮询接口不能缓存
  assert.equal(calls, 3, 'polled endpoints must always refetch');
});

test('prefetch fills the cache without throwing', async () => {
  state.token = '';
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json([{ id: 9 }]); };
  prefetch('/products?t=prefetch');
  await new Promise(r => setTimeout(r, 20));
  const got = await api('/products?t=prefetch');
  assert.deepEqual(got, [{ id: 9 }]);
  assert.equal(calls, 1, 'prefetch should warm the cache');
});

test('page entry data is cached: me / product / profile / order', async () => {
  // 线上一次往返 0.7–3 秒，这些是切页入口接口，必须命中缓存才算达标。
  state.token = 'entry-user';
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ ok: true }); };
  for (const path of ['/me', '/product?id=5', '/profile?id=9003', '/order?id=8', '/want?id=3', '/ticket?id=2']){
    await api(path);
    await api(path);
  }
  assert.equal(calls, 6, 'each entry endpoint should be fetched exactly once');
});

test('concurrent identical GETs share one request', async () => {
  state.token = 'dedupe-user';
  let calls = 0, release;
  globalThis.fetch = () => { calls++; return new Promise(resolve => { release = resolve; }); };
  const first = api('/product?id=77');
  const second = api('/product?id=77');
  await new Promise(r => setTimeout(r, 10));
  assert.equal(calls, 1, 'in-flight request must be reused');
  release(Response.json({ id: 77 }));
  assert.deepEqual(await first, { id: 77 });
  assert.deepEqual(await second, { id: 77 });
});
