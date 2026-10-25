import { it, expect, vi } from 'vitest';

/** 新前端不把线上已有所有者降成普通用户；未知角色依然不给界面管理权限。 */
it('保留线上owner角色等级，未知角色按普通用户展示', async () => {
  const { roleRank } = await import('./session.js');
  expect(roleRank({ role: 'owner' })).toBe(4);
  expect(roleRank({ role: 'admin' })).toBe(2);
  expect(roleRank({ role: 'invented-role' })).toBe(0);
});
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
