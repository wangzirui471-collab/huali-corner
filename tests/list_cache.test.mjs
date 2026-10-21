import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';

globalThis.window = { crypto: webcrypto };
globalThis.sessionStorage = { getItem(){ return null; } };

const { api, prefetch } = await import('../web 7M/src/core/http.js');
const { state } = await import('../web 7M/src/core/state.js');

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
