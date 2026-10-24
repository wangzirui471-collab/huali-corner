import { it, expect, vi } from 'vitest';
/** 配置查询尚未结束时完成登录，旧查询的取消不能遮住新身份页面。 */
it('账号切换造成的启动取消不显示为连接故障', async () => {
  vi.resetModules();
  localStorage.clear();
  sessionStorage.clear();
  let finish = /** @type {(response:Response)=>void} */ (() => {});
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    ),
  );
  const { session, initializeSession, acceptLogin } = await import('./session.js');
  const starting = initializeSession();
  acceptLogin({ token: 'new-login', user: { id: 18, nickname: '新身份' } });
  finish(Response.json({ auth_mode: 'password' }));
  await starting;
  expect(session.me?.id).toBe(18);
  expect(session.startupError).toBe('');
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});
