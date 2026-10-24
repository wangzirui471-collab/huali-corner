<script setup>
import { computed, onMounted, onScopeDispose, ref } from "vue";
import AppButton from "@/shared/ui/AppButton.vue";
import AppDialog from "@/shared/ui/AppDialog.vue";
import Icon from "./PreviewIcon.vue";
import "./preview.css";

const logo = "/brand/logo-lockup.svg";
const query = ref(""),
  searchTerm = ref(""),
  category = ref("all"),
  sort = ref("new"),
  mode = ref("all");
const favorites = ref(new Set()),
  count = ref(8),
  notice = ref(""),
  selected = ref(null);
const categories = [
  { id: "all", name: "全部好物" },
  { id: "books", name: "二手书" },
  { id: "living", name: "宿舍生活" },
  { id: "sports", name: "运动户外" },
  { id: "electronics", name: "数码电子" },
];
const shortcuts = [
  { label: "教材专区", icon: "book", category: "books", tone: "purple" },
  { label: "宿舍好物", icon: "sofa", category: "living", tone: "sand" },
  { label: "运动装备", icon: "ball", category: "sports", tone: "green" },
  { label: "数码闲置", icon: "laptop", category: "electronics", tone: "blue" },
  { label: "免费送", icon: "gift", mode: "free", tone: "rose" },
  { label: "求购互助", icon: "chat", tone: "purple" },
  { label: "我的收藏", icon: "heart", mode: "favorites", tone: "rose" },
  { label: "我的订单", icon: "bag", tone: "sand" },
  { label: "帮助售后", icon: "help", tone: "green" },
];
const products = [
  {
    id: 1,
    image: 0,
    title: "计算机网络 第 7 版 · 少量笔记",
    price: 18,
    original: 59,
    category: "books",
    condition: "九成新",
    region: "图书馆门口",
    seller: "小林同学",
    time: "刚刚",
    delivery: "可自提 / 送货 ¥2",
  },
  {
    id: 2,
    image: 1,
    title: "Python 程序设计，入门课教材",
    price: 15,
    original: 49,
    category: "books",
    condition: "八成新",
    region: "教学楼 A 栋",
    seller: "阿晴",
    time: "5 分钟前",
    delivery: "校内自提",
  },
  {
    id: 3,
    image: 6,
    title: "实木折叠小凳，宿舍收纳不占地",
    price: 29,
    original: 69,
    category: "living",
    condition: "九成新",
    region: "学生中心",
    seller: "柚子",
    time: "12 分钟前",
    delivery: "校内自提",
  },
  {
    id: 4,
    image: 7,
    title: "暖光台灯 · 陪你读完下一本书",
    price: 25,
    original: 79,
    category: "living",
    condition: "九成新",
    region: "图书馆门口",
    seller: "小满",
    time: "20 分钟前",
    delivery: "可自提 / 送货 ¥3",
  },
  {
    id: 5,
    image: 2,
    title: "数据结构（C 语言版），无缺页",
    price: 16,
    original: 45,
    category: "books",
    condition: "八成新",
    region: "教学楼 B 栋",
    seller: "阿哲",
    time: "30 分钟前",
    delivery: "校内自提",
  },
  {
    id: 6,
    image: 8,
    title: "羽毛球拍一支，周末一起上场",
    price: 38,
    original: 128,
    category: "sports",
    condition: "正常使用痕迹",
    region: "体育馆门口",
    seller: "橙子",
    time: "45 分钟前",
    delivery: "校内自提",
  },
  {
    id: 7,
    image: 9,
    title: "桌面收纳抽屉，整理一点小空间",
    price: 12,
    original: 32,
    category: "living",
    condition: "九成新",
    region: "学生中心",
    seller: "星期六",
    time: "1 小时前",
    delivery: "可自提 / 送货 ¥2",
  },
  {
    id: 8,
    image: 3,
    title: "高等数学上册，送给需要的同学",
    price: 0,
    original: 49,
    category: "books",
    condition: "有笔记，已说明",
    region: "教学楼 A 栋",
    seller: "阿禾",
    time: "1 小时前",
    delivery: "物品免费 · 校内自提",
  },
  {
    id: 9,
    image: 12,
    title: "有线键盘，打字手感轻盈",
    price: 45,
    original: 129,
    category: "electronics",
    condition: "九成新",
    region: "图书馆门口",
    seller: "小周",
    time: "2 小时前",
    delivery: "校内自提",
  },
  {
    id: 10,
    image: 10,
    title: "三本课外书，希望故事继续",
    price: 35,
    original: 108,
    category: "books",
    condition: "九成新",
    region: "学生中心",
    seller: "木木",
    time: "2 小时前",
    delivery: "可自提 / 送货 ¥2",
  },
  {
    id: 11,
    image: 14,
    title: "深蓝双肩包，洗净后免费转让",
    price: 0,
    original: 99,
    category: "living",
    condition: "有使用痕迹",
    region: "图书馆门口",
    seller: "陈同学",
    time: "3 小时前",
    delivery: "物品免费 · 校内自提",
  },
  {
    id: 12,
    image: 15,
    title: "空白线圈本，留给新的学期",
    price: 8,
    original: 18,
    category: "living",
    condition: "未使用",
    region: "教学楼 B 栋",
    seller: "向日葵",
    time: "3 小时前",
    delivery: "校内自提",
  },
];
const filtered = computed(() => {
  const result = products.filter(
    (p) =>
      (category.value === "all" || p.category === category.value) &&
      (!searchTerm.value || p.title.includes(searchTerm.value)) &&
      (mode.value !== "free" || p.price === 0) &&
      (mode.value !== "favorites" || favorites.value.has(p.id)),
  );
  return sort.value === "price"
    ? [...result].sort((a, b) => a.price - b.price)
    : result;
});
const visible = computed(() => filtered.value.slice(0, count.value));
const activeFilters = computed(
  () => !!searchTerm.value || category.value !== "all" || mode.value !== "all",
);
const slides = ref([0, 0]),
  paused = ref([false, false]),
  hovered = ref([false, false]),
  focused = ref([false, false]);
const reduced = ref(false),
  hidden = ref(false);
const panels = [
  {
    label: "书籍与生活专题",
    tone: "study",
    tag: "旧书新故事",
    slides: [
      {
        title: "教材不必买新的",
        description: "对上版次，好书接着读。",
        cta: "去挑一本",
        category: "books",
      },
      {
        title: "小空间，也有新灵感",
        description: "把宿舍生活整理得刚刚好。",
        cta: "逛宿舍好物",
        category: "living",
      },
      {
        title: "下一场，接着上场",
        description: "运动装备，遇见新的搭档。",
        cta: "看看装备",
        category: "sports",
      },
    ],
  },
  {
    label: "校园循环与互助专题",
    tone: "campus",
    tag: "好物留在华立",
    slides: [
      {
        title: "轻装出发，好物接棒",
        description: "闲置有去处，同学有照应。",
        cta: "逛逛校园好物",
        category: "all",
      },
      {
        title: "免费送，也有新故事",
        description: "物品免费，交付费用看详情。",
        cta: "看看免费好物",
        mode: "free",
      },
      {
        title: "分享一件闲置的故事",
        description: "三张实拍，清楚介绍。",
        cta: "发布我的闲置",
        action: "发布",
      },
    ],
  },
];
const nav = [
  { icon: "home", label: "逛逛" },
  { icon: "chat", label: "社区" },
  { icon: "plus", label: "发布" },
  { icon: "forum", label: "论坛" },
  { icon: "chat", label: "消息" },
];
let timers = [],
  noticeTimer,
  media;
/** 预览反馈只存在内存，不创建账号或业务记录。 */
function announce(message) {
  notice.value = message;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => {
    notice.value = "";
  }, 3500);
}
/** 合成搜索保留用户输入，显式提交后更新商品区域。 */
function search() {
  searchTerm.value = query.value.trim();
  count.value = 8;
}
/** 清除筛选并恢复预览列表。 */
function reset() {
  query.value = "";
  searchTerm.value = "";
  category.value = "all";
  mode.value = "all";
  count.value = 8;
}
/** 本地筛选不调用真实接口；非首页入口给出明确的预览范围。 */
function activate(item) {
  if (item.category || item.mode) {
    category.value = item.category || "all";
    mode.value = item.mode || "all";
    count.value = 8;
  } else
    announce(
      "这是首页预览稿；" +
        (item.label || item.action) +
        "入口在正式页面中保留。",
    );
}
/** 独立收藏只切换当前预览状态，不影响用户原有收藏。 */
function favorite(product) {
  const next = new Set(favorites.value);
  if (next.has(product.id)) {
    next.delete(product.id);
    announce("已取消收藏");
  } else {
    next.add(product.id);
    announce("已收藏，预览状态仅保留在当前页面");
  }
  favorites.value = next;
}
/** 手动换页暂停自动播放，避免刚选中的内容立即切走。 */
function move(index, delta) {
  slides.value[index] = (slides.value[index] + delta + 3) % 3;
  paused.value[index] = true;
}
/** 聚焦离开整个专题时，才解除键盘交互导致的临时暂停。 */
function leaveFocus(event, index) {
  if (!event.currentTarget.contains(event.relatedTarget))
    focused.value[index] = false;
}
/** 自动轮播同时尊重用户暂停、悬停、聚焦、后台与减少动态效果设置。 */
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
/** 后台不切换，避免用户回来时失去阅读位置。 */
function visibility() {
  hidden.value = document.hidden;
}
/** 系统减少动态效果时禁止自动轮播。 */
function motion(event) {
  reduced.value = event.matches;
}
onMounted(() => {
  media = window.matchMedia("(prefers-reduced-motion: reduce)");
  reduced.value = media.matches;
  media.addEventListener("change", motion);
  document.addEventListener("visibilitychange", visibility);
  visibility();
  timers = [7000, 8500].map((delay, index) =>
    setInterval(() => tick(index), delay),
  );
});
onScopeDispose(() => {
  timers.forEach(clearInterval);
  clearTimeout(noticeTimer);
  media?.removeEventListener("change", motion);
  document.removeEventListener("visibilitychange", visibility);
});
</script>

<template>
  <div class="review-strip">
    <div>
      <span class="review-dot" />首页预览 · 方案 A<span class="review-context"
        >先看布局，再决定应用</span
      ><span class="review-note">演示内容 · 不连接真实交易</span>
    </div>
  </div>
  <header class="site-header">
    <div class="header-main wrap">
      <a class="brand" href="#" aria-label="华立转角首页" @click.prevent="reset"
        ><img :src="logo" alt="华立转角" width="142" height="45"
      /></a>
      <div class="campus-name">广州校区<span>计算机工程学院试点</span></div>
      <form class="search-box" role="search" @submit.prevent="search">
        <Icon name="search" :size="19" /><input
          v-model="query"
          type="search"
          aria-label="搜索校园闲置"
          placeholder="搜教材、台灯、羽毛球拍…"
        /><button type="submit">搜索</button>
      </form>
      <button
        class="header-link"
        aria-label="取货清单"
        @click="activate({ label: '取货清单' })"
      >
        <Icon name="cart" /><span>取货清单</span>
      </button>
      <button
        class="account"
        aria-label="登录或注册"
        @click="activate({ label: '登录或注册' })"
      >
        <Icon name="user" :size="19" />
      </button>
    </div>
    <nav class="desktop-nav wrap" aria-label="主导航">
      <button class="current" @click="reset">逛逛</button
      ><button @click="activate({ label: '社区' })">校园社区</button
      ><button @click="activate({ label: '论坛' })">论坛与互助</button
      ><button @click="activate({ label: '消息' })">消息</button
      ><span class="nav-spacer" /><span class="simulation"
        ><span />模拟交易，不扣真实款项</span
      ><AppButton @click="activate({ label: '发布闲置' })"
        ><Icon name="plus" :size="18" />发布闲置</AppButton
      >
    </nav>
  </header>
  <main class="wrap main-content">
    <nav class="category-row" aria-label="商品分类">
      <button
        v-for="item in categories"
        :key="item.id"
        :class="{ active: category === item.id && mode === 'all' }"
        :aria-pressed="category === item.id && mode === 'all'"
        @click="activate({ category: item.id })"
      >
        {{ item.name }}
      </button>
    </nav>
    <nav class="shortcut-grid" aria-label="快捷入口">
      <button
        v-for="item in shortcuts"
        :key="item.label"
        @click="activate(item)"
      >
        <span class="shortcut-icon" :class="item.tone"
          ><Icon :name="item.icon" :size="22" /></span
        ><span>{{ item.label }}</span>
      </button>
    </nav>
    <div class="promo-grid">
      <section
        v-for="(panel, index) in panels"
        :key="panel.label"
        class="promo-panel"
        :class="panel.tone"
        :aria-label="panel.label"
        @mouseenter="hovered[index] = true"
        @mouseleave="hovered[index] = false"
        @focusin="focused[index] = true"
        @focusout="leaveFocus($event, index)"
      >
        <div class="promo-copy">
          <span class="promo-tag">{{ panel.tag }}</span>
          <h2>{{ panel.slides[slides[index]].title }}</h2>
          <p>{{ panel.slides[slides[index]].description }}</p>
          <button
            class="text-link"
            @click="activate(panel.slides[slides[index]])"
          >
            {{ panel.slides[slides[index]].cta
            }}<Icon name="arrow" :size="16" />
          </button>
        </div>
        <div v-if="index === 0" class="books-art" aria-hidden="true">
          <span class="book book-back">慢 慢 读</span
          ><span class="book book-front">旧书<br />新故事<i>ZJ</i></span>
        </div>
        <svg
          v-else
          class="campus-art"
          viewBox="0 0 170 115"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M14 100h145M28 100V42l28-13 26 13v58M90 100V52l27-13 27 13v48M37 52h11v13H37zm23 0h11v13H60zm-23 24h11v13H37zm23 0h11v13H60zm40-15h10v13h-10zm24 0h10v13h-10zm-24 24h10v15h-10zm24 0h10v15h-10M56 29V12m0 0h20l-6 7H56"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linejoin="round"
          />
          <circle cx="134" cy="19" r="10" fill="currentColor" opacity=".2" />
        </svg>
        <div class="promo-controls">
          <span class="slide-position"
            >{{ slides[index] + 1 }} <span>/ 3</span></span
          ><button
            :aria-label="'上一张' + panel.label"
            @click="move(index, -1)"
          >
            <Icon name="left" :size="15" /></button
          ><button
            :aria-label="
              (paused[index] ? '继续' : '暂停') + panel.label + '轮播'
            "
            :aria-pressed="paused[index]"
            @click="paused[index] = !paused[index]"
          >
            <Icon :name="paused[index] ? 'play' : 'pause'" :size="15" /></button
          ><button :aria-label="'下一张' + panel.label" @click="move(index, 1)">
            <Icon name="right" :size="15" />
          </button>
        </div>
      </section>
    </div>
    <section id="products" aria-labelledby="feed-title">
      <header class="feed-heading">
        <div>
          <h1 id="feed-title">
            {{
              mode === "favorites"
                ? "我的收藏"
                : mode === "free"
                  ? "免费好物"
                  : searchTerm
                    ? "找到这些好物"
                    : "校园好物，刚刚上新"
            }}<span class="heading-mark" />
          </h1>
          <p>
            {{
              searchTerm
                ? "搜索“" + searchTerm + "” · "
                : "好物不闲置，生活有转角 · "
            }}{{ filtered.length }} 件演示商品
          </p>
        </div>
        <div class="sort-control">
          <label class="sr-only" for="sort">商品排序</label
          ><select id="sort" v-model="sort">
            <option value="new">最新发布</option>
            <option value="price">价格从低到高</option>
          </select>
        </div>
      </header>
      <div v-if="activeFilters" class="filter-summary">
        <span
          >正在查看：{{
            searchTerm || categories.find((c) => c.id === category)?.name
          }}{{
            mode === "free"
              ? " · 免费送"
              : mode === "favorites"
                ? " · 已收藏"
                : ""
          }}</span
        ><button aria-label="清除搜索条件" @click="reset">
          清除条件<Icon name="close" :size="14" />
        </button>
      </div>
      <div v-if="visible.length" class="product-grid">
        <article
          v-for="product in visible"
          :key="product.id"
          class="product-card"
        >
          <div class="cover-wrap">
            <button
              class="product-cover"
              :aria-label="'查看' + product.title"
              @click="selected = product"
            >
              <span
                class="photo-sprite"
                role="img"
                :aria-label="product.title + '的演示配图'"
                :style="{
                  backgroundPosition: `${((product.image % 4) * 100) / 3}% ${(Math.floor(product.image / 4) * 100) / 3}%`,
                }"
              /></button
            ><span v-if="product.price === 0" class="free-tag">免费送</span
            ><button
              class="favorite-button"
              :class="{ saved: favorites.has(product.id) }"
              :aria-label="
                (favorites.has(product.id) ? '取消收藏' : '收藏') +
                product.title
              "
              :aria-pressed="favorites.has(product.id)"
              @click="favorite(product)"
            >
              <Icon name="heart" :size="20" />
            </button>
          </div>
          <div class="product-copy">
            <button class="product-title" @click="selected = product">
              {{ product.title }}
            </button>
            <div class="condition-line">
              <span>{{ product.condition }}</span
              ><span class="place"
                ><Icon name="pin" :size="12" />{{ product.region }}</span
              >
            </div>
            <div class="price-line">
              <strong v-if="product.price"
                ><small>¥</small>{{ product.price }}<span>.00</span></strong
              ><strong v-else class="free-price">免费送</strong
              ><del v-if="product.price">¥{{ product.original }}</del>
            </div>
            <p class="delivery-line">{{ product.delivery }}</p>
            <div class="seller-line">
              <span class="seller-avatar">{{ product.seller.slice(0, 1) }}</span
              ><span>{{ product.seller }}</span
              ><time>{{ product.time }}</time>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">
        <Icon :name="mode === 'favorites' ? 'heart' : 'search'" :size="36" />
        <h2>
          {{
            mode === "favorites"
              ? "先收藏几件喜欢的好物吧"
              : "还没找到合适的好物"
          }}
        </h2>
        <p>换个关键词或分类，再逛逛校园里的闲置。</p>
        <AppButton variant="secondary" @click="reset">看看全部好物</AppButton>
      </div>
      <div class="feed-end">
        <AppButton
          v-if="count < filtered.length"
          variant="secondary"
          @click="count += 4"
          >再逛逛 · 加载更多<Icon name="arrow" :size="16"
        /></AppButton>
        <p v-else>好物都在这里了，改天再来逛逛。</p>
      </div>
    </section>
    <footer class="site-footer">
      <img :src="logo" alt="华立转角" width="118" /><span
        >闲置有去处，同学有照应。</span
      ><button @click="activate({ label: '帮助与售后' })">
        帮助与售后<Icon name="arrow" :size="14" />
      </button>
    </footer>
  </main>
  <nav class="bottom-nav" aria-label="手机主导航">
    <button
      v-for="(item, index) in nav"
      :key="item.label"
      :class="{ current: index === 0, publish: index === 2 }"
      @click="index === 0 ? reset() : activate(item)"
    >
      <span><Icon :name="item.icon" :size="22" /></span>{{ item.label }}
    </button>
  </nav>
  <div
    class="feedback"
    :class="{ shown: notice }"
    role="status"
    aria-live="polite"
  >
    {{ notice }}
  </div>
  <AppDialog :open="!!selected" title="商品卡片预览" @close="selected = null"
    ><template v-if="selected"
      ><div
        class="detail-preview photo-sprite"
        role="img"
        :aria-label="selected.title + '的演示配图'"
        :style="{
          backgroundPosition: `${((selected.image % 4) * 100) / 3}% ${(Math.floor(selected.image / 4) * 100) / 3}%`,
        }"
      />
      <h2>{{ selected.title }}</h2>
      <p class="detail-price">
        {{ selected.price ? "¥" + selected.price + ".00" : "免费送" }}
      </p>
      <p>{{ selected.condition }} · {{ selected.region }}</p>
      <p>{{ selected.delivery }}</p>
      <p class="dialog-note">
        当前只确认首页布局与交互。这里是演示内容，不会下单或改动真实数据。
      </p>
      <AppButton @click="selected = null">继续逛逛</AppButton></template
    ></AppDialog
  >
</template>
