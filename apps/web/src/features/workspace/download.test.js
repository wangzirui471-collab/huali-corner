import { afterEach, expect, it, vi } from 'vitest';
import { session } from '@/shared/legacy/session.js';
import { downloadOperation } from './download.js';

/** 清理合成会话和网络替身，不访问真实备份接口。 */
afterEach(() => {
  session.token = '';
  vi.unstubAllGlobals();
});

/** 读取下载错误正文期间切换账号，旧 401 不能清除新登录状态。 */
it('下载迟到的错误正文不能影响新账号', async () => {
  session.token = 'old-session';
  const response = new Response(null, {
    status: 401,
    headers: { 'content-type': 'application/json' },
  });
  vi.spyOn(response, 'json').mockImplementation(async () => {
    session.token = 'new-session';
    return { error: '旧会话失效' };
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => response),
  );
  await expect(downloadOperation('audit')).rejects.toMatchObject({ name: 'AbortError' });
  expect(session.token).toBe('new-session');
});
