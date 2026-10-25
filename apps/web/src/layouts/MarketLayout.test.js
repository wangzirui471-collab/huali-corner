import { afterEach, expect, it, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import MarketLayout from './MarketLayout.vue';

vi.mock('@/shared/legacy/session.js', () => ({
  session: {
    token: '',
    ready: true,
    me: null,
    epoch: 0,
    cart: [],
    startupError: '',
    recoveryCode: '',
  },
  api: vi.fn(),
  initializeSession: () => Promise.resolve(),
  syncSession: vi.fn(),
  roleRank: () => 0,
}));
/** 恢复构建环境，避免测试把生产开关泄露给其他用例。 */
afterEach(() => vi.unstubAllEnvs());
/** 默认和未知模式不挂载生产AI，显式legacy-stream才打开新宠物。 */
it.each([
  ['', false],
  ['faq', false],
  ['legacy-stream', true],
])('构建模式 %s 的宠物启用为 %s', async (mode, enabled) => {
  vi.stubEnv('VITE_HUALI_ASSISTANT_MODE', mode);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  });
  await router.push('/');
  const wrapper = shallowMount(MarketLayout, {
    global: { plugins: [router], stubs: { PetWidget: true } },
  });
  expect(wrapper.find('pet-widget-stub').exists()).toBe(enabled);
  wrapper.unmount();
});
