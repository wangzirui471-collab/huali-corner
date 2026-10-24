import { it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import PublishPage from './PublishPage.vue';
const { api } = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/shared/legacy/session.js', () => ({
  api,
  session: { me: { id: 9, score: 100 }, config: {} },
  readStorage: () => null,
  writeStorage: () => true,
}));
/** 缺少三视图时不能上传或发布；失败后标题与价格仍留在表单。 */
it('三视图不全时保留输入并阻止业务写请求', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PublishPage }],
  });
  await router.push('/');
  await router.isReady();
  const wrapper = mount(PublishPage, { global: { plugins: [router] } });
  const title = wrapper.find('input[maxlength="80"]');
  await title.setValue('不丢失的教材标题');
  await wrapper.find('textarea').setValue('合成测试教材介绍');
  await wrapper.find('input[placeholder="例如：图书馆门口"]').setValue('图书馆门口');
  const bookFields = wrapper.findAll('input[maxlength="120"]');
  await bookFields[0].setValue('第二版');
  await bookFields[1].setValue('合成出版社');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(api).not.toHaveBeenCalled();
  expect(/** @type {HTMLInputElement} */ (title.element).value).toBe('不丢失的教材标题');
  expect(wrapper.text()).toContain('请分别选择正面、侧面、顶部实拍');
  wrapper.unmount();
});
