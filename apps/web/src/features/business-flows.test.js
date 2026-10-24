import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { ApiError } from '@/shared/http/client.js';
import MessagesPage from './community/MessagesPage.vue';
import ProductPage from './catalog/ProductPage.vue';
import DossierPage from './workspace/DossierPage.vue';
import HomePage from './catalog/HomePage.vue';
const { api, session, cache } = vi.hoisted(() => ({
  api: vi.fn(),
  session: {
    token: 'synthetic-session',
    epoch: 0,
    me: { id: 7, role: 'user' },
    config: {},
    cart: [],
    listMemory: new Map(),
  },
  cache: new Map(),
}));
vi.mock('@/shared/legacy/session.js', () => ({
  api,
  session,
  roleRank: () => 0,
  changeCart: vi.fn(),
  readStorage: (/** @type {string} */ key) => cache.get(key) || null,
  writeStorage: (/** @type {string} */ key, /** @type {string|null} */ value) => {
    if (value === null) cache.delete(key);
    else cache.set(key, value);
    return true;
  },
}));
/** 用真实 Vue 路由和控件验证页面输入输出；网络只返回明确的旧接口合成 DTO。 @param {import('vue').Component} component 页面。 @param {string} path 路由。 @param {string} url 测试地址。 */
async function page(component, path, url) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path, component },
      { path: '/:pathMatch(.*)*', component: { template: '<div/>' } },
    ],
  });
  await router.push(url);
  await router.isReady();
  const wrapper = mount(component, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}
describe('旧业务页面的关键恢复行为', () => {
  /** 专题可独立暂停，暂停后跨越多个周期保持内容，继续后仍能切换。 */
  it('首页专题允许独立暂停与继续', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    api.mockReset();
    session.listMemory.clear();
    api.mockResolvedValue([]);
    const wrapper = await page(HomePage, '/', '/');
    try {
      const panel = wrapper.find('[aria-label="书籍与生活专题"]');
      const title = panel.find('h2').text();
      const pause = panel.find('button[aria-label="暂停书籍与生活专题轮播"]');
      expect(pause.exists()).toBe(true);
      await pause.trigger('click');
      await vi.advanceTimersByTimeAsync(16000);
      expect(panel.find('h2').text()).toBe(title);
      await panel.find('button[aria-label="继续书籍与生活专题轮播"]').trigger('click');
      await vi.advanceTimersByTimeAsync(7100);
      expect(panel.find('h2').text()).not.toBe(title);
    } finally {
      wrapper.unmount();
      vi.useRealTimers();
    }
  });
  /** 追加失败不能隐藏已读商品，重试仍请求失败的第二页而不跳页或重复第一页。 */
  it('首页追加失败保留列表并重试同一页', async () => {
    api.mockReset();
    session.listMemory.clear();
    api
      .mockResolvedValueOnce(
        Array.from({ length: 24 }, (_, index) => ({
          id: index + 1,
          title: '已读商品' + index,
          photos: [],
        })),
      )
      .mockRejectedValueOnce(new Error('第二页连接失败'))
      .mockResolvedValueOnce([{ id: 25, title: '下一页商品', photos: [] }]);
    const wrapper = await page(HomePage, '/', '/');
    try {
      const more = wrapper.findAll('button').find((button) => button.text() === '加载更多好物');
      await more?.trigger('click');
      await flushPromises();
      expect(wrapper.findAll('.product-card')).toHaveLength(24);
      expect(wrapper.text()).toContain('第二页连接失败');
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '重试加载更多')
        ?.trigger('click');
      await flushPromises();
      expect(wrapper.findAll('.product-card')).toHaveLength(25);
      const requests = api.mock.calls.filter(([path]) => path.startsWith('/products?'));
      expect(requests).toHaveLength(3);
      expect(
        requests.map(([path]) =>
          new URL('http://local.invalid/api' + path).searchParams.get('page'),
        ),
      ).toEqual(['1', '2', '2']);
    } finally {
      wrapper.unmount();
    }
  });
  /** 收藏变化使其他筛选缓存失效；当前页返回仍保留已确认状态，不被旧快照覆盖。 */
  it('收藏更新后不会恢复其他筛选下的旧收藏状态', async () => {
    api.mockReset();
    session.listMemory.clear();
    session.listMemory.set('/?category=books', {
      at: Date.now(),
      page: 1,
      exhausted: true,
      items: [{ id: 11, favorited: false }],
    });
    api
      .mockResolvedValueOnce([
        { id: 11, seller_id: 8, title: '合成教材', photos: [], favorited: false },
      ])
      .mockResolvedValueOnce({ ok: true });
    const first = await page(HomePage, '/', '/');
    try {
      await first.find('.favorite-button').trigger('click');
      await flushPromises();
      expect(session.listMemory.has('/?category=books')).toBe(false);
      expect(first.find('.favorite-button').attributes('aria-pressed')).toBe('true');
    } finally {
      first.unmount();
    }
    const second = await page(HomePage, '/', '/');
    try {
      expect(second.find('.favorite-button').attributes('aria-pressed')).toBe('true');
      expect(api).toHaveBeenCalledTimes(2);
    } finally {
      second.unmount();
    }
  });
  /** 相同账号从详情返回时恢复已有追加流，不强制回到首次列表查询。 */
  it('返回首页恢复列表快照', async () => {
    api.mockReset();
    session.listMemory.clear();
    api.mockResolvedValue([{ id: 11, title: '已浏览的教材', photos: [] }]);
    const first = await page(HomePage, '/', '/');
    expect(first.text()).toContain('已浏览的教材');
    first.unmount();
    const second = await page(HomePage, '/', '/');
    expect(second.text()).toContain('已浏览的教材');
    expect(api).toHaveBeenCalledTimes(1);
    second.unmount();
  });

  /** 写消息返回 502 时保留正文，点击重试沿用同一 key，成功后才清输入。 */
  it('消息未知结果重试沿用原键', async () => {
    api.mockReset();
    cache.clear();
    let writes = 0;
    api.mockImplementation(async (path, options) => {
      if (path === '/rooms')
        return { joined: [{ id: 9, name: '合成私聊', role: 'member', kind: 'private' }] };
      if (path === '/notifications') return { items: [], unread: 0 };
      if (path.startsWith('/messages/receipts')) return { readers: [], total: 1 };
      if (path === '/messages' && options?.body) {
        if (++writes === 1)
          throw new ApiError('提交结果未确认', 'NETWORK_ERROR', 502, undefined, undefined, true);
        return { ok: true };
      }
      return [];
    });
    const wrapper = await page(MessagesPage, '/messages/:id', '/messages/9');
    await wrapper.find('textarea').setValue('只发一次的消息');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(/** @type {HTMLTextAreaElement} */ (wrapper.find('textarea').element).value).toBe(
      '只发一次的消息',
    );
    expect(wrapper.text()).toContain('按原键重试');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    const sent = api.mock.calls.filter(([path, options]) => path === '/messages' && options?.body);
    expect(sent).toHaveLength(2);
    expect(sent[0][1].body.key).toBe(sent[1][1].body.key);
    expect(/** @type {HTMLTextAreaElement} */ (wrapper.find('textarea').element).value).toBe('');
    wrapper.unmount();
  });
  /** 收藏状态采用旧 favorited 字段，取消时明确提交 on:false。 */
  it('商品已收藏时提交取消收藏', async () => {
    api.mockReset();
    api.mockImplementation(async (path) =>
      path.startsWith('/products?')
        ? []
        : {
            id: 11,
            seller_id: 8,
            title: '合成教材',
            status: 'available',
            favorited: true,
            photos: [],
          },
    );
    const wrapper = await page(ProductPage, '/products/:id', '/products/11');
    const favorite = wrapper.findAll('button').find((button) => button.text() === '取消收藏');
    expect(favorite).toBeDefined();
    await favorite?.trigger('click');
    await flushPromises();
    expect(api).toHaveBeenCalledWith(
      '/react',
      expect.objectContaining({ body: { product_id: 11, kind: 'favorite', on: false } }),
    );
    wrapper.unmount();
  });
  /** 敏感档案不是普通预取，打开路由不产生审计访问；明确点击才读取。 */
  it('敏感档案必须显式点击读取', async () => {
    api.mockReset();
    api.mockResolvedValue({ user: { id: 8, nickname: '档案对象' }, products: [], orders: [] });
    const wrapper = await page(DossierPage, '/workspace/users/:id', '/workspace/users/8');
    expect(api).not.toHaveBeenCalled();
    await wrapper.find('button').trigger('click');
    await flushPromises();
    expect(api).toHaveBeenCalledWith(
      '/user/dossier?id=8',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    wrapper.unmount();
  });
});
