<script setup>
import { computed, onMounted, onScopeDispose, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session } from '@/shared/legacy/session.js';

import { rows, number } from '@/shared/legacy/dto.js';
import { useLoad } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import AppButton from '@/shared/ui/AppButton.vue';
import ProductCard from './ProductCard.vue';
import AppIcon from '@/shared/ui/AppIcon.vue';
import InlineNotice from '@/shared/ui/InlineNotice.vue';
import './catalog-home.css';
const route = useRoute(),
  router = useRouter(),
  page = ref(1),
  exhausted = ref(false);
const category = computed(() => String(route.query.category || ''));
const categories = [
  { id: '', name: '推荐' },
  { id: 'books', name: '二手书' },
  { id: 'living', name: '宿舍生活' },
  { id: 'sports', name: '运动好物' },
  { id: 'electronics', name: '电子产品' },
];
const slides = ref([0, 0]),
  paused = ref([false, false]),
  hovered = ref([false, false]),
  focused = ref([false, false]);
const reduced = ref(false),
  hidden = ref(false),
  failedAppend = ref(false);
const shortcuts = [
  { label: '教材专区', icon: 'book', tone: 'purple', to: '/?category=books' },
  { label: '宿舍好物', icon: 'sofa', tone: 'sand', to: '/?category=living' },
  { label: '运动装备', icon: 'ball', tone: 'green', to: '/?category=sports' },
  { label: '数码闲置', icon: 'laptop', tone: 'blue', to: '/?category=electronics' },
  { label: '免费送', icon: 'gift', tone: 'rose', to: '/?free=1' },
  { label: '求购互助', icon: 'chat', tone: 'purple', to: '/forum/wants' },
  { label: '我的收藏', icon: 'heart', tone: 'rose', to: '/favorites' },
  { label: '我的订单', icon: 'bag', tone: 'sand', to: '/orders' },
  { label: '帮助售后', icon: 'help', tone: 'green', to: '/support' },
];
const panels = [
  [
    {
      title: '教材不必买新的',
      lead: '旧书，也有新故事',
      description: '按版次找书 · 当面看书况',
      to: '/?category=books',
      label: '去挑一本',
      art: 'books',
    },
    {
      title: '宿舍好物，轻松焕新',
      lead: '小小空间，也有新灵感',
      description: '桌椅、台灯和收纳',
      to: '/?category=living',
      label: '逛逛宿舍好物',
      art: 'living',
    },
    {
      title: '运动装备，接着上场',
      lead: '下一场，和同学一起',
      description: '让热爱继续',
      to: '/?category=sports',
      label: '看看运动装备',
      art: 'sports',
    },
  ],
  [
    {
      title: '好物留在华立',
      lead: '毕业季 · 轻装出发',
      description: '分享清仓信息，找需要它的人',
      to: '/community',
      label: '去校园社区',
      art: 'campus',
    },
    {
      title: '免费送，也有新故事',
      lead: '同学之间 · 分享一份善意',
      description: '物品免费转让 · 交付方式看详情',
      to: '/?free=1',
      label: '看看免费好物',
      art: 'free',
    },
    {
      title: '闲置，遇见新主人',
      lead: '整理生活 · 从一件闲置开始',
      description: '拍下真实书况，清楚介绍好物',
      to: '/publish',
      label: '发布我的闲置',
      art: 'publish',
    },
  ],
];
/** @type {ReturnType<typeof setInterval>[]} 当前页轮播定时器。 */
let timers = [];
/** @type {MediaQueryList|undefined} 系统减少动态效果设置。 */
let media;
/** 后台停留时保持当前专题，不让用户返回时丢失阅读上下文。 */
function visibility() {
  hidden.value = document.hidden;
}
/** 系统减少动态效果设置生效时，不自动切换内容。 @param {MediaQueryListEvent} event 设置变更。 */
function motion(event) {
  reduced.value = event.matches;
}
/** 两个窗口分别暂停，聚焦、悬停与后台状态共同控制自动播放。 @param {number} index 专题窗口。 */
function tick(index) {
  if (
    !paused.value[index] &&
    !hovered.value[index] &&
    !focused.value[index] &&
    !reduced.value &&
    !hidden.value
  )
    slides.value[index] = (slides.value[index] + 1) % 3;
}
/** 手动选择内容后暂停，避免立即被自动播放切走。 @param {number} index 窗口。 @param {number} delta 前后步长。 */
function move(index, delta) {
  slides.value[index] = (slides.value[index] + delta + 3) % 3;
  paused.value[index] = true;
}
/** 只有焦点离开整个专题才解除临时暂停。 @param {FocusEvent} event 焦点变化。 @param {number} index 窗口。 */
function leaveFocus(event, index) {
  if (
    event.currentTarget instanceof window.HTMLElement &&
    !(
      event.relatedTarget instanceof window.Node &&
      event.currentTarget.contains(event.relatedTarget)
    )
  )
    focused.value[index] = false;
}
/** 复用同一中文名称构造分区和控制名称，便于屏幕阅读器识别。 @param {number} index 窗口。 */
function panelLabel(index) {
  return index === 0 ? '书籍与生活专题' : '校园循环与互助专题';
}
onMounted(() => {
  media = window.matchMedia('(prefers-reduced-motion: reduce)');
  reduced.value = media.matches;
  media.addEventListener('change', motion);
  visibility();
  document.addEventListener('visibilitychange', visibility);
  timers = [7000, 8500].map((delay, index) => setInterval(() => tick(index), delay));
});
onScopeDispose(() => {
  timers.forEach(clearInterval);
  media?.removeEventListener('change', motion);
  document.removeEventListener('visibilitychange', visibility);
});
/** @type {import('@/shared/legacy/dto.js').Row[]} 当前追加流，只追加未出现的商品。 */
let accumulated = [];
const cacheKey = route.fullPath,
  epoch = session.epoch;
let snapshot = session.listMemory.get(cacheKey);
if (snapshot && Date.now() - snapshot.at > 120000) snapshot = undefined;
/** 只保留当前身份的短期列表内存；换账号的卸载不能把旧列表写回新会话。 */
onScopeDispose(() => {
  if (epoch !== session.epoch || !accumulated.length) return;
  session.listMemory.set(cacheKey, {
    items: accumulated,
    page: page.value,
    exhausted: exhausted.value,
    at: Date.now(),
  });
  while (session.listMemory.size > 6) {
    const oldest = session.listMemory.keys().next().value;
    if (oldest === undefined) break;
    session.listMemory.delete(oldest);
  }
});
const catalog = useLoad(async (signal) => {
  if (snapshot) {
    page.value = snapshot.page;
    exhausted.value = snapshot.exhausted;
    accumulated = snapshot.items;
    snapshot = undefined;
    return accumulated;
  }
  const query = new URLSearchParams({
    q: String(route.query.q || ''),
    category: category.value,
    sort: String(route.query.sort || ''),
  });
  const local = route.query.free === '1' || route.path === '/favorites';
  if (route.path === '/favorites') query.set('favorite', '1');
  if (!local) {
    query.set('page', String(page.value));
    query.set('limit', '24');
  }
  const result = rows(await api('/products?' + query, { signal }));
  const items =
    route.query.free === '1' ? result.filter((product) => number(product, 'price') === 0) : result;
  exhausted.value = local || items.length < 24;
  accumulated =
    page.value === 1
      ? items
      : [
          ...accumulated,
          ...items.filter(
            (product) => !accumulated.some((old) => number(old, 'id') === number(product, 'id')),
          ),
        ];
  return accumulated;
});
/** 地址承载筛选，返回详情时由路由保存列表滚动位置。 @param {string} value 分类。 */
function selectCategory(value) {
  void router.push({
    path: '/',
    query: { ...route.query, category: value || undefined, free: undefined },
  });
}
/** 失败不推进页码，重试仍请求同一页。 */
async function more() {
  page.value++;
  await catalog.reload();
  failedAppend.value = !!catalog.error.value;
  if (catalog.error.value) page.value--;
}
/** 主动刷新从第一页重新读取；不复用短期列表快照。 */
async function refresh() {
  snapshot = undefined;
  failedAppend.value = false;
  page.value = 1;
  accumulated = [];
  session.listMemory.delete(cacheKey);
  await catalog.reload();
}
/** 收藏成功同步当前列表和短期快照；收藏页取消后即时移除，失败则保持旧内容。 @param {{id:number,on:boolean}} change 已确认的旧接口结果。 */
function favoriteChanged(change) {
  // 其他筛选快照仍含旧收藏状态；仅保留接下来保存的当前页已确认结果。
  session.listMemory.clear();
  accumulated = accumulated.map((product) =>
    number(product, 'id') === change.id ? { ...product, favorited: change.on } : product,
  );
  if (route.path === '/favorites' && !change.on)
    accumulated = accumulated.filter((product) => number(product, 'id') !== change.id);
  catalog.data.value = accumulated;
}
const retained = computed(() => !!catalog.data.value?.length && !catalog.forbidden.value);
/** 重试追加仍走下一页；其他错误重新查询第一页，避免错误的页码或旧查询覆盖。 */
async function retry() {
  if (failedAppend.value) await more();
  else await refresh();
}
/** 清除 URL 条件，收藏页仍保持在收藏上下文。 */
function clearFilters() {
  void router.push({ path: route.path === '/favorites' ? '/favorites' : '/', query: {} });
}
</script>
<template>
  <section class="home-page">
    <template v-if="route.path !== '/favorites'">
      <nav class="category-row" aria-label="商品分类">
        <button
          v-for="item in categories"
          :key="item.id"
          :class="{ active: category === item.id && route.query.free !== '1' }"
          :aria-pressed="category === item.id && route.query.free !== '1'"
          @click="selectCategory(item.id)"
        >
          {{ item.name }}
        </button>
      </nav>
      <nav class="shortcut-grid" aria-label="快捷入口">
        <RouterLink v-for="item in shortcuts" :key="item.to" :to="item.to"
          ><span class="shortcut-icon" :class="item.tone"
            ><AppIcon :name="item.icon" :size="22" /></span
          ><span>{{ item.label }}</span></RouterLink
        >
      </nav>
      <div class="promo-grid">
        <section
          v-for="(panel, index) in panels"
          :key="index"
          class="promo-panel"
          :class="index === 0 ? 'study' : 'campus-promo'"
          :aria-label="panelLabel(index)"
          @mouseenter="hovered[index] = true"
          @mouseleave="hovered[index] = false"
          @focusin="focused[index] = true"
          @focusout="leaveFocus($event, index)"
        >
          <div class="promo-copy">
            <span class="promo-tag">{{ panel[slides[index]].lead }}</span>
            <h2>{{ panel[slides[index]].title }}</h2>
            <p>{{ panel[slides[index]].description }}</p>
            <RouterLink class="text-link" :to="panel[slides[index]].to"
              >{{ panel[slides[index]].label }}<AppIcon name="arrow" :size="16"
            /></RouterLink>
          </div>
          <div v-if="index === 0" class="books-art" aria-hidden="true">
            <span class="book book-back">慢 慢 读</span
            ><span class="book book-front">旧书<br />新故事<i>ZJ</i></span>
          </div>
          <svg v-else class="campus-art" viewBox="0 0 170 115" fill="none" aria-hidden="true">
            <path
              d="M14 100h145M28 100V42l28-13 26 13v58M90 100V52l27-13 27 13v48M37 52h11v13H37zm23 0h11v13H60zm-23 24h11v13H37zm23 0h11v13H60zm40-15h10v13h-10zm24 0h10v13h-10zm-24 24h10v15h-10zm24 0h10v15h-10M56 29V12m0 0h20l-6 7H56"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linejoin="round"
            />
            <circle cx="134" cy="19" r="10" fill="currentColor" opacity=".2" />
          </svg>
          <div class="promo-controls">
            <span class="slide-position">{{ slides[index] + 1 }} <span>/ 3</span></span
            ><button :aria-label="'上一张' + panelLabel(index)" @click="move(index, -1)">
              <AppIcon name="left" :size="15" /></button
            ><button
              :aria-label="(paused[index] ? '继续' : '暂停') + panelLabel(index) + '轮播'"
              :aria-pressed="paused[index]"
              @click="paused[index] = !paused[index]"
            >
              <AppIcon :name="paused[index] ? 'play' : 'pause'" :size="15" /></button
            ><button :aria-label="'下一张' + panelLabel(index)" @click="move(index, 1)">
              <AppIcon name="right" :size="15" />
            </button>
          </div>
        </section>
      </div>
    </template>
    <header class="feed-heading">
      <div>
        <h1>
          {{
            route.path === '/favorites'
              ? '我的收藏'
              : route.query.free === '1'
                ? '免费好物'
                : route.query.q
                  ? '找到这些好物'
                  : '校园好物，刚刚上新'
          }}<span class="heading-mark" />
        </h1>
        <p>
          {{ route.query.q ? '搜索：' + route.query.q : '好物不闲置，生活有转角'
          }}<span v-if="catalog.data.value?.length">
            · 已加载 {{ catalog.data.value.length }} 件</span
          >
        </p>
      </div>
      <div class="home-feed-tools">
        <AppButton variant="quiet" :loading="catalog.loading.value" @click="refresh"
          >刷新</AppButton
        >
        <div class="sort-control">
          <select
            aria-label="商品排序"
            :value="String(route.query.sort || '')"
            @change="
              router.push({
                query: {
                  ...route.query,
                  sort: /** @type {HTMLSelectElement} */ ($event.target).value,
                },
              })
            "
          >
            <option value="">最新发布</option>
            <option value="price">价格升序</option>
          </select>
        </div>
      </div>
    </header>
    <div v-if="route.query.q || route.query.category || route.query.free" class="filter-summary">
      <span
        >已设置{{
          route.query.q ? '关键词：' + route.query.q : route.query.free ? '免费送' : '分类筛选'
        }}</span
      ><button aria-label="清除搜索条件" @click="clearFilters">
        清除条件<AppIcon name="close" :size="14" />
      </button>
    </div>
    <LoadBoundary
      :loading="catalog.loading.value && !retained"
      :error="retained ? '' : catalog.error.value"
      :forbidden="catalog.forbidden.value"
      :empty="!!catalog.data.value && !catalog.data.value.length"
      @retry="retry"
    >
      <div class="product-grid" :aria-busy="catalog.loading.value">
        <ProductCard
          v-for="product in catalog.data.value"
          :key="number(product, 'id')"
          :product="product"
          @favorite-changed="favoriteChanged"
        />
      </div>
      <InlineNotice
        v-if="retained && catalog.error.value"
        tone="error"
        title="读取未完成，已保留当前商品"
        >{{ catalog.error.value }}</InlineNotice
      >
      <div class="feed-end">
        <AppButton
          v-if="retained && catalog.error.value"
          variant="secondary"
          :loading="catalog.loading.value"
          @click="retry"
          >{{ failedAppend ? '重试加载更多' : '重试刷新' }}</AppButton
        ><AppButton
          v-else-if="!exhausted"
          variant="secondary"
          :loading="catalog.loading.value"
          @click="more"
          >加载更多好物</AppButton
        >
        <p v-else class="muted">已经看到全部好物了</p>
      </div>
    </LoadBoundary>
  </section>
</template>
