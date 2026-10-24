import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import ProductCard from './ProductCard.vue';
const { api, session } = vi.hoisted(() => ({
  api: vi.fn(),
  session: {
    token: 'test-session',
    epoch: 0,
    me: /** @type {import('@/shared/legacy/dto.js').Row|null} */ ({ id: 7 }),
  },
}));
vi.mock('@/shared/legacy/session.js', () => ({ api, session }));
/** 每例恢复独立合成身份，不连接任何真实业务服务。 */
beforeEach(() => {
  api.mockReset();
  session.me = { id: 7 };
  session.token = 'test-session';
});
/** 真实路由承载卡片链接和登录返回地址，卡片不嵌套交互控件。 @param {import('@/shared/legacy/dto.js').Row} [extra] 合成商品覆盖字段。 */
async function card(extra = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  });
  await router.push('/?category=books');
  await router.isReady();
  const wrapper = mount(ProductCard, {
    props: {
      product: {
        id: 11,
        seller_id: 8,
        title: '合成教材',
        favorited: true,
        price: 1800,
        delivery: 'both',
        delivery_fee: 200,
        photos: [],
        ...extra,
      },
    },
    global: { plugins: [router] },
  });
  return { wrapper, router };
}
/** 收藏使用旧 DTO 和绝对 on 值，成功后发出结果供首页同步内存快照。 */
it('独立收藏按钮提交旧协议并同步成功状态', async () => {
  api.mockResolvedValue({ ok: true });
  const { wrapper } = await card();
  try {
    const button = wrapper.find('button[aria-label="取消收藏合成教材"]');
    expect(button.exists()).toBe(true);
    expect(button.element.closest('a')).toBeNull();
    await button.trigger('click');
    await flushPromises();
    expect(api).toHaveBeenCalledWith(
      '/react',
      expect.objectContaining({ body: { product_id: 11, kind: 'favorite', on: false } }),
    );
    expect(wrapper.find('.favorite-button').attributes('aria-pressed')).toBe('false');
    expect(wrapper.emitted('favorite-changed')?.[0]).toEqual([{ id: 11, on: false }]);
    expect(wrapper.text()).toContain('送货 ¥2.00');
  } finally {
    wrapper.unmount();
  }
});
/** 写入失败保留旧收藏状态和可见错误，不向父列表假报成功。 */
it('收藏失败保留原状态并展示持久错误', async () => {
  api.mockRejectedValue(new Error('收藏服务暂不可用'));
  const { wrapper } = await card();
  try {
    expect(wrapper.find('.favorite-button').exists()).toBe(true);
    await wrapper.find('.favorite-button').trigger('click');
    await flushPromises();
    expect(wrapper.find('.favorite-button').attributes('aria-pressed')).toBe('true');
    expect(wrapper.text()).toContain('收藏服务暂不可用');
    expect(wrapper.emitted('favorite-changed')).toBeUndefined();
  } finally {
    wrapper.unmount();
  }
});
/** 游客收藏先登录并保留返回路径，不发出匿名写入。 */
it('游客收藏导航到登录且保留来源', async () => {
  session.me = null;
  session.token = '';
  const { wrapper, router } = await card();
  try {
    expect(wrapper.find('.favorite-button').exists()).toBe(true);
    await wrapper.find('.favorite-button').trigger('click');
    await flushPromises();
    expect(api).not.toHaveBeenCalled();
    expect(router.currentRoute.value.path).toBe('/login');
    expect(router.currentRoute.value.query.next).toBe('/?category=books');
  } finally {
    wrapper.unmount();
  }
});
/** 演示图只匹配明确的同源演示资源，不将真实私密图片或外站图片替换成假商品。 */
it.each([
  { simulation: true, url: '/assets/book0.svg', expected: true },
  { simulation: true, url: '/media/private-photo', expected: false },
  { simulation: true, url: 'https://outside.invalid/assets/book0.svg', expected: false },
])('演示配图边界 $url', async ({ simulation, url, expected }) => {
  const { wrapper } = await card({ simulation, photos: [{ url }] });
  try {
    expect(wrapper.find('.catalog-demo-photo').exists()).toBe(expected);
  } finally {
    wrapper.unmount();
  }
});
