import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import SupportPage from '../SupportPage.vue';
import { api, session } from '@/shared/legacy/session.js';
import { saveAssistantDraft, consumeAssistantDraft } from './handoff-draft.js';

// 只替换未迁移的工单网络，保持真实问答草稿和会话反应逻辑。
vi.mock('@/shared/legacy/session.js', async (importOriginal) => {
  const original = /** @type {typeof import('@/shared/legacy/session.js')} */ (
    await importOriginal()
  );
  return { ...original, api: vi.fn().mockResolvedValue([]) };
});
/** 用例结束清理合成身份，不留下任何人工草稿。 */
afterEach(() => {
  session.token = '';
  session.me = null;
  session.epoch++;
});

/** 人工表单只预填可编辑原问题；仅用户确认后才调用原 tickets 唯一写入口。 */
it('转人工草稿可编辑且确认前不提交工单或开客服会话', async () => {
  session.token = 'handoff-token';
  session.me = { id: 20 };
  session.epoch++;
  const originalQuestion = '付款会真实扣款吗？';
  saveAssistantDraft(originalQuestion);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/support/new', component: SupportPage },
      { path: '/support/:id', component: { template: '<div>工单详情</div>' } },
      { path: '/support', component: { template: '<div>工单列表</div>' } },
    ],
  });
  await router.push('/support/new');
  await router.isReady();
  const wrapper = mount(SupportPage, { global: { plugins: [router] } });
  await flushPromises();
  expect(wrapper.find('textarea').element.value).toBe(originalQuestion);
  expect(wrapper.findComponent({ name: 'AssistantPanel' }).exists()).toBe(false);
  expect(consumeAssistantDraft()).toBe('');
  expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.body)).toEqual([]);
  await wrapper.find('input[maxlength="120"]').setValue('付款规则咨询');
  await wrapper.find('textarea').setValue('我已检查并补充的问题');
  vi.mocked(api).mockResolvedValueOnce({ id: 77 });
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(api).toHaveBeenCalledWith(
    '/tickets',
    expect.objectContaining({
      body: {
        type: 'other',
        subject: '付款规则咨询',
        body: '我已检查并补充的问题',
        order_id: null,
        product_id: null,
      },
    }),
  );
  expect(
    vi
      .mocked(api)
      .mock.calls.some(([path]) => path === '/support/room' || path === '/support/claim'),
  ).toBe(false);
  expect(router.currentRoute.value.path).toBe('/support/77');
  wrapper.unmount();
});
