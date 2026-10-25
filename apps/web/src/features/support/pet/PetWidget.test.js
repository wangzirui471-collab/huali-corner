import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { nextTick } from 'vue';
import PetWidget from './PetWidget.vue';
import { session } from '@/shared/legacy/session.js';
import { consumeAssistantDraft } from '../assistant/handoff-draft.js';

/** 挂载真实Teleport和路由，检查全局浮窗可访问行为。 */
async function widget() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/products/:id', component: { template: '<div>商品</div>' } },
      { path: '/orders', component: { template: '<div>订单</div>' } },
      { path: '/support/new', component: { template: '<div>表单</div>' } },
    ],
  });
  await router.push('/');
  const wrapper = mount(PetWidget, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}
/** 使用合成会话及真实旧偏好协议。 */
beforeEach(() => {
  session.token = 'synthetic';
  session.me = { id: 9 };
  session.epoch++;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url) =>
      Promise.resolve(
        Response.json(
          String(url).endsWith('/prefs')
            ? {
                synced: true,
                skin: 'custom',
                scale: 1.2,
                hidden: false,
                life: true,
                custom_url: '/media/pet_0123456789abcdef0123456789abcdef',
                custom_w: 300,
                custom_h: 200,
              }
            : { ok: true },
        ),
      ),
    ),
  );
});
/** 清除浮层、测试替身及合成账号。 */
afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
  session.token = '';
  session.me = null;
  session.epoch++;
  localStorage.removeItem('hc-vue-pet-position');
  vi.unstubAllGlobals();
});

/** Escape应只关闭非模态窗并把焦点还给开启者，纯文本不能执行HTML。 */
it('点击抚摸开启对话、Escape关闭并恢复焦点，保留完整旧AI入口', async () => {
  const wrapper = await widget();
  const launcher = /** @type {HTMLButtonElement} */ (document.querySelector('[data-pet-launcher]'));
  launcher.focus();
  launcher.click();
  await nextTick();
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  expect(document.body.textContent).toContain('摸摸收到啦');
  expect(document.querySelector('a[href="/legacy-ai.html#home"]')).not.toBeNull();
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await nextTick();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(document.activeElement).toBe(launcher);
  wrapper.unmount();
});
/** 只保存允许的偏好字段；缩放不可覆盖旧自定义形象和生活开关。 */
it('读取custom形象，保存缩放保留旧自定义字段且不写聊天或token', async () => {
  const wrapper = await widget();
  expect(document.querySelector('img')?.getAttribute('src')).toBe(
    '/media/pet_0123456789abcdef0123456789abcdef',
  );
  /** @type {HTMLButtonElement|null} */ (document.querySelector('[data-pet-launcher]'))?.click();
  await nextTick();
  const scale = /** @type {HTMLInputElement} */ (document.querySelector('[aria-label="宠物大小"]'));
  scale.value = '1.4';
  scale.dispatchEvent(new window.Event('input', { bubbles: true }));
  scale.dispatchEvent(new window.Event('change', { bubbles: true }));
  await flushPromises();
  const calls = vi.mocked(fetch).mock.calls;
  const saved = calls.find(([url]) => String(url).endsWith('/prefs/save'));
  expect(saved).toBeDefined();
  expect(JSON.parse(String(saved?.[1]?.body))).toEqual({
    skin: 'custom',
    scale: 1.4,
    hidden: false,
    life: true,
    custom_url: '/media/pet_0123456789abcdef0123456789abcdef',
    custom_w: 300,
    custom_h: 200,
  });
  wrapper.unmount();
});
/** 主指针拖后浏览器合成click不能误开聊天，缩小视口后重新夹紧。 */
it('拖动后阻止误点击，取消和卸载移除全局指针监听', async () => {
  const wrapper = await widget();
  const launcher = /** @type {HTMLButtonElement} */ (document.querySelector('[data-pet-launcher]'));
  launcher.dispatchEvent(
    new window.PointerEvent('pointerdown', {
      pointerId: 1,
      clientX: 100,
      clientY: 100,
      button: 0,
      bubbles: true,
    }),
  );
  window.dispatchEvent(
    new window.PointerEvent('pointermove', { pointerId: 1, clientX: 200, clientY: 200 }),
  );
  window.dispatchEvent(
    new window.PointerEvent('pointerup', { pointerId: 1, clientX: 200, clientY: 200 }),
  );
  launcher.click();
  await nextTick();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  launcher.click();
  await nextTick();
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  wrapper.unmount();
  expect(document.querySelector('[data-pet-launcher]')).toBeNull();
});

/** 完成DTO的HTML只显示为文字；商品编号严格检查且人工入口没有自动业务写入。 */
it('流式完成按纯文本呈现metadata，人工仅带原问题到表单', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url, options) => {
      if (!String(url).endsWith('/stream'))
        return Promise.resolve(Response.json({ synced: false }));
      const turn = JSON.parse(String(options.body)).client_turn_id;
      const result = {
        answer: '<img src=x onerror=alert(1)>回答',
        action: 'transfer',
        mode: 'chat',
        products: [
          { id: 12, title: '台灯' },
          { id: 'javascript:evil()', title: '危险编号' },
        ],
        orders: [{ id: 9, title: '合成订单', status_label: '待付款' }],
        sources: [{ title: '<script>危险来源</script>' }],
        suggestions: ['建议问题'],
      };
      return Promise.resolve(
        new Response(
          `event: turn\ndata: ${JSON.stringify({ client_turn_id: turn })}\n\nevent: delta\ndata: ${JSON.stringify({ text: '部分' })}\n\nevent: done\ndata: ${JSON.stringify({ client_turn_id: turn, result })}\n\n`,
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
    }),
  );
  const wrapper = await widget();
  /** @type {HTMLButtonElement|null} */ (document.querySelector('[data-pet-launcher]'))?.click();
  await nextTick();
  const input = /** @type {HTMLTextAreaElement} */ (document.querySelector('textarea'));
  input.value = '我需要人工确认';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  document
    .querySelector('form')
    ?.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await flushPromises();
  expect(document.body.textContent).toContain('<img src=x onerror=alert(1)>回答');
  expect(document.querySelector('script')).toBeNull();
  expect(document.querySelector('img')).toBeNull();
  expect(document.querySelector('a[href="/products/12"]')).not.toBeNull();
  expect(document.querySelector('a[href="/orders"]')?.textContent).toContain('合成订单');
  expect(document.body.textContent).not.toContain('危险编号');
  const handoff = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === '转人工',
  );
  handoff?.click();
  await flushPromises();
  expect(consumeAssistantDraft()).toBe('我需要人工确认');
  expect(
    vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/stream')),
  ).toHaveLength(1);
  expect(
    vi.mocked(fetch).mock.calls.some(([url]) => /tickets|support\/room/.test(String(url))),
  ).toBe(false);
  wrapper.unmount();
});

/** 未读取到旧账号偏好前不可用默认值覆盖其custom、life等字段。 */
it('偏好读取进行中禁止保存，防止默认值覆盖原设置', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => new Promise(() => {})),
  );
  const wrapper = await widget();
  /** @type {HTMLButtonElement|null} */ (document.querySelector('[data-pet-launcher]'))?.click();
  await nextTick();
  const scale = /** @type {HTMLInputElement} */ (document.querySelector('[aria-label="宠物大小"]'));
  expect(scale.disabled).toBe(true);
  expect(vi.mocked(fetch).mock.calls).toHaveLength(1);
  wrapper.unmount();
});

/** 抚摸提示短暂出现后自行退出，避免长期遮挡页面。 */
it('抚摸提示到期隐藏，卸载后不再保留提示计时器', async () => {
  const wrapper = await widget();
  vi.useFakeTimers();
  /** @type {HTMLButtonElement|null} */ (document.querySelector('[data-pet-launcher]'))?.click();
  await nextTick();
  expect(document.querySelector('.zj-pet-feedback')).not.toBeNull();
  await vi.advanceTimersByTimeAsync(4500);
  expect(document.querySelector('.zj-pet-feedback')).toBeNull();
  wrapper.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
