import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { nextTick } from 'vue';
import AssistantPanel from './AssistantPanel.vue';
import { session } from '@/shared/legacy/session.js';
import { consumeAssistantDraft, saveAssistantDraft } from './handoff-draft.js';

/** 构造带来源的 HTTP 成功响应，模型 HTML 作为未经执行的普通文本。 @param {string} turnId 请求轮次。 */
function success(turnId) {
  return Response.json({
    code: 'OK',
    message: '',
    error: null,
    request_id: 'panel-test',
    meta: { schema_version: 'v1', simulation: true },
    data: {
      client_turn_id: turnId,
      answer_text: '<img src=x onerror=alert(1)>公开规则',
      mode: 'mock',
      sources: [
        {
          document_id: 'faq-demo',
          title: '<b>来源标题</b>',
          version: 'demo',
          content: '<script>unsafe()</script>来源正文',
        },
      ],
      handoff: { recommended: true, reason: '需要人工确认', next_path: '/support/new' },
    },
  });
}
/** 创建只读导航，方便验证人工入口只保存草稿且不触发业务写入。 */
async function panel() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/support', component: AssistantPanel },
      { path: '/support/new', component: { template: '<div>人工表单</div>' } },
    ],
  });
  await router.push('/support');
  await router.isReady();
  const wrapper = mount(AssistantPanel, { global: { plugins: [router] } });
  return { wrapper, router };
}
/** 每例使用新的合成账号上下文。 */
beforeEach(() => {
  session.token = 'panel-token';
  session.me = { id: 9 };
  session.epoch++;
});
/** 撤销全局网络替身并清理合成私密内存。 */
afterEach(() => {
  session.token = '';
  session.me = null;
  session.epoch++;
  vi.unstubAllGlobals();
});

/** 网络失败保留问题，用户显式重试沿用原键；内容一旦修改就创建新键。 */
it.each([502, 503])('%i HTML 保留问题与原 UUID，编辑后生成新 UUID且不自动重试', async (status) => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response('<html>proxy</html>', { status })));
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('怎样约定时间？');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(wrapper.find('textarea').element.value).toBe('怎样约定时间？');
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(session.token).toBe('panel-token');
  const first = JSON.parse(fetcher.mock.calls[0][1].body);
  await wrapper.find('[data-action="retry"]').trigger('click');
  await flushPromises();
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(first);
  await wrapper.find('textarea').setValue('如何取消预约？');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetcher.mock.calls[2][1].body).client_turn_id).not.toBe(first.client_turn_id);
  wrapper.unmount();
});
/** 权限失败如实显示且保留输入，不把无权误认为需要清除账号。 */
it('403 显示无权状态并保留问题', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      Response.json(
        {
          code: 'FORBIDDEN',
          message: '没有使用权限',
          data: null,
          error: null,
          request_id: 'forbidden',
          meta: { schema_version: 'v1', simulation: true },
        },
        { status: 403 },
      ),
    ),
  );
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('规则？');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('没有使用权限');
  expect(wrapper.find('textarea').element.value).toBe('规则？');
  expect(session.token).toBe('panel-token');
  wrapper.unmount();
});
/** 答案与来源完全按文本显示，转人工只导航和交接可检查的问题草稿。 */
it('模型 HTML 不执行，转人工不建工单或会话且草稿不进 URL', async () => {
  const fetcher = vi
    .fn()
    .mockImplementation((_input, options) =>
      Promise.resolve(success(JSON.parse(options.body).client_turn_id)),
    );
  vi.stubGlobal('fetch', fetcher);
  const { wrapper, router } = await panel();
  await wrapper.find('textarea').setValue('我想确认交付约定');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>公开规则');
  expect(wrapper.text()).toContain('<script>unsafe()</script>来源正文');
  expect(wrapper.find('img').exists()).toBe(false);
  expect(wrapper.find('script').exists()).toBe(false);
  expect(wrapper.text()).toContain('模拟回答');
  await wrapper.find('[data-action="handoff"]').trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.fullPath).toBe('/support/new');
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(consumeAssistantDraft()).toBe('我想确认交付约定');
  expect(consumeAssistantDraft()).toBe('');
  wrapper.unmount();
});
/** 账号变化时取消网络并清除输入、答案、失败键和人工草稿，迟到回复无效。 */
it('账号切换丢弃迟到响应并清空私密内存', async () => {
  /** @type {(value: Response) => void} 手动恢复忽略取消的旧请求。 */
  let finish = () => undefined;
  const fetcher = vi.fn().mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('旧账号的问题');
  await wrapper.find('form').trigger('submit');
  const previousTurn = JSON.parse(fetcher.mock.calls[0][1].body).client_turn_id;
  session.token = 'other-token';
  session.me = { id: 10 };
  session.epoch++;
  await nextTick();
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  finish(success(previousTurn));
  await flushPromises();
  expect(wrapper.find('textarea').element.value).toBe('');
  expect(wrapper.text()).not.toContain('<img src=x onerror=alert(1)>公开规则');
  expect(consumeAssistantDraft()).toBe('');
  wrapper.unmount();
});
/** 离开页面也中止请求；迟到异常不能在已卸载面板中展示。 */
it('卸载面板取消网络请求', async () => {
  const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('取消检查');
  await wrapper.find('form').trigger('submit');
  wrapper.unmount();
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
});
/** 空白问题不请求模型；未登录页面明确说明身份限制。 */
it('空白及无会话不会发送问答请求', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('   ');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('请输入 1—800 字的问题');
  expect(fetcher).not.toHaveBeenCalled();
  session.token = '';
  await nextTick();
  expect(wrapper.text()).toContain('请先登录');
  expect(wrapper.find('textarea').exists()).toBe(false);
  wrapper.unmount();
});
/** 已转人工但未消费的草稿不能在切换账号后恢复，即使再切回旧账号。 */
it('人工草稿按账号隔离且退出后不恢复', () => {
  saveAssistantDraft('旧账号私人问题');
  session.token = 'new-account';
  session.me = { id: 10 };
  session.epoch++;
  expect(consumeAssistantDraft()).toBe('');
  session.token = 'panel-token';
  session.me = { id: 9 };
  session.epoch++;
  expect(consumeAssistantDraft()).toBe('');
});
/** 明确身份失效才退出，旧轮次及问题随身份失效立即从私密内存清除。 */
it('明确 401 清会话和页面内存', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    Response.json(
      {
        code: 'UNAUTHORIZED',
        message: '会话已失效',
        data: null,
        error: null,
        request_id: 'expired',
        meta: { schema_version: 'v1', simulation: true },
      },
      { status: 401 },
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('过期会话的问题');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(session.token).toBe('');
  expect(wrapper.find('textarea').exists()).toBe(false);
  expect(wrapper.text()).not.toContain('过期会话的问题');
  wrapper.unmount();
});
/** 成功后重复查询同一问题仍是原轮次，允许服务端返回缓存；编辑内容才开始新轮次。 */
it('成功后再次查询相同问题沿用原 UUID，编辑后才生成新 UUID', async () => {
  const fetcher = vi
    .fn()
    .mockImplementation((_input, options) =>
      Promise.resolve(success(JSON.parse(options.body).client_turn_id)),
    );
  vi.stubGlobal('fetch', fetcher);
  const { wrapper } = await panel();
  await wrapper.find('textarea').setValue('付款会真实扣款吗？');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  const first = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(wrapper.text()).toContain('模拟回答');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(first);
  await wrapper.find('textarea').setValue('发布商品需要几张照片？');
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetcher.mock.calls[2][1].body).client_turn_id).not.toBe(first.client_turn_id);
  wrapper.unmount();
});
