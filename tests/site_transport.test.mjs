import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';
globalThis.window = {crypto: webcrypto};
globalThis.sessionStorage = {getItem(){return null;}};
const {api} = await import('../web 7M/src/core/http.js');
const {state} = await import('../web 7M/src/core/state.js');
const {randomSaltHex, pbkdf2Hex} = await import('../web 7M/src/core/pbkdf2.js');

test('registration generates a cryptographically random 16-byte salt', () => {
  const a = randomSaltHex(), b = randomSaltHex();
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.notEqual(a, b);
});

test('HTML error pages yield a readable HTTP error without losing the session', async () => {
  state.token = 'test-session';
  globalThis.fetch = async () => new Response('<!DOCTYPE html><h1>Worker error</h1>', {
    status:503, headers:{'Content-Type':'text/html'}
  });
  await assert.rejects(api('/auth/login', {}), err => {
    assert.equal(err.status,503);
    assert.doesNotMatch(err.message,/Unexpected token|DOCTYPE|not valid JSON/);
    assert.match(err.message,/服务|网络|稍后/);
    return true;
  });
  assert.equal(state.token,'test-session');
});

test('HTML returned as success is rejected as a protocol error', async () => {
  globalThis.fetch = async () => new Response('<!DOCTYPE html><h1>SPA</h1>', {
    status:200, headers:{'Content-Type':'text/html'}
  });
  await assert.rejects(api('/auth/login', {}), err => {
    assert.equal(err.status,200);
    assert.match(err.message,/接口|服务/);
    return true;
  });
});

test('JSON application errors preserve message and status', async () => {
  globalThis.fetch = async () => Response.json({error:'账号、密码或恢复码不正确'},{status:401});
  await assert.rejects(api('/auth/login',{}),err => err.status===401 && err.message==='账号、密码或恢复码不正确');
});

test('normal JSON responses and bearer headers remain compatible', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url,'/api/me');
    assert.equal(options.headers.Authorization,'Bearer test-session');
    return Response.json({id:2,nickname:'同学'});
  };
  assert.deepEqual(await api('/me'),{id:2,nickname:'同学'});
});
