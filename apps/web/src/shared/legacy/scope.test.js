import { it, expect, vi } from 'vitest';
import { effectScope } from 'vue';
import { useLegacyApi } from './use-task.js';
const { api, session } = vi.hoisted(() => ({
  api: vi.fn(),
  session: { token: 'first', epoch: 1 },
}));
vi.mock('./session.js', () => ({ api, session }));
/** 离开页面或切换账号后，图片读取等旧任务不能借新身份继续发写请求。 */
it('页面取消后拒绝尚未发出的后续请求', async () => {
  const scope = effectScope();
  const request = scope.run(() => useLegacyApi());
  scope.stop();
  session.token = 'second';
  session.epoch++;
  await expect(request?.('/upload', { body: { content: 'old-file' } })).rejects.toMatchObject({
    name: 'AbortError',
  });
  expect(api).not.toHaveBeenCalled();
});
