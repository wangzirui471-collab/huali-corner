<script setup>
import './business.css';
import './market-chrome.css';
import AppIcon from '@/shared/ui/AppIcon.vue';
import { onMounted, onScopeDispose, ref, watch } from 'vue';
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router';
import { api, initializeSession, session, syncSession, roleRank } from '@/shared/legacy/session.js';
import { row, number, text } from '@/shared/legacy/dto.js';
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import PageState from '@/shared/ui/PageState.vue';
const router = useRouter(),
  route = useRoute(),
  query = ref('');
const logo = '/brand/logo-lockup.svg';
const badge = ref(0),
  badgeController = new AbortController();
let badgeLoading = false;
/** 角标只在登录且窗口可见时查询；迟到响应由客户端与取消信号拦截。 */
async function refreshBadge() {
  if (document.hidden || !session.token || !session.ready || badgeLoading) return;
  badgeLoading = true;
  try {
    const result = row(await api('/badges', { signal: badgeController.signal }));
    badge.value = number(result, 'notifications') + number(result, 'chat');
  } catch {
    /* 角标故障不覆盖页面；消息页保留可重试错误。 */
  } finally {
    badgeLoading = false;
  }
}
const badgeTimer = setInterval(refreshBadge, 30000);
watch(
  () => session.epoch,
  () => {
    badge.value = 0;
    void refreshBadge();
  },
);
watch(
  () => route.query.q,
  (value) => {
    query.value = String(value || '');
  },
  { immediate: true },
);
const slots = [
  { to: '/', label: '逛逛', icon: 'home' },
  { to: '/community', label: '社区', icon: 'chat' },
  { to: '/publish', label: '发布', icon: 'plus' },
  { to: '/forum', label: '论坛', icon: 'forum' },
  { to: '/messages', label: '消息', icon: 'chat' },
];
/** 子页面仍标明所属主导航，首页只在根路径选中。 @param {string} to 导航路径。 */
function navCurrent(to) {
  return to === '/' ? route.path === '/' : route.path === to || route.path.startsWith(to + '/');
}
/** 搜索状态保存在地址，详情返回后可以恢复搜索与列表。 */
function search() {
  void router.push({ path: '/', query: query.value ? { q: query.value } : {} });
}
onMounted(() => {
  void initializeSession().then(refreshBadge);
  window.addEventListener('storage', syncSession);
});
onScopeDispose(() => {
  window.removeEventListener('storage', syncSession);
  clearInterval(badgeTimer);
  badgeController.abort();
});
</script>
<template>
  <header class="market-header">
    <div class="header-inner">
      <RouterLink to="/" class="brand"
        ><img :src="logo" width="142" height="45" alt="华立转角" /></RouterLink
      ><span class="campus">广州校区<small>计算机工程学院试点</small></span>
      <form role="search" class="search-bar" @submit.prevent="search">
        <AppIcon name="search" :size="19" /><input
          v-model="query"
          type="search"
          aria-label="搜索闲置"
          placeholder="搜教材、台灯、羽毛球拍…"
        /><button type="submit">搜索</button>
      </form>
      <RouterLink
        class="header-cart"
        to="/cart"
        :aria-label="'取货清单，' + session.cart.length + '件商品'"
        ><AppIcon name="cart" /><span class="cart-label">取货清单</span
        ><b v-if="session.cart.length" class="cart-count">{{ session.cart.length }}</b></RouterLink
      >
      <RouterLink
        class="account-link"
        :to="session.me ? '/me' : '/login'"
        :aria-label="session.me ? '我的个人中心' : '登录或注册'"
        ><span class="avatar"
          ><template v-if="session.me">{{
            text(session.me, 'nickname', '我').slice(0, 1)
          }}</template
          ><AppIcon v-else name="user" :size="19" /></span
        ><span class="account-name" :title="text(session.me, 'nickname')">{{
          session.me ? text(session.me, 'nickname') : '登录 / 注册'
        }}</span></RouterLink
      >
    </div>
    <nav class="desktop-nav" aria-label="主导航">
      <RouterLink
        v-for="item in slots.filter((item) => item.to !== '/publish')"
        :key="item.to"
        :to="item.to"
        :class="{ current: navCurrent(item.to) }"
        >{{ item.label }}</RouterLink
      ><RouterLink class="secondary-nav" to="/orders">我的订单</RouterLink
      ><RouterLink class="secondary-nav" to="/support">帮助与售后</RouterLink
      ><RouterLink v-if="roleRank() >= 1" to="/workspace">工作台</RouterLink
      ><span class="nav-spacer" /><span class="simulation-note">模拟交易，不扣真实款项</span
      ><RouterLink class="publish-link" to="/publish"
        ><AppIcon name="plus" :size="18" />发布闲置</RouterLink
      >
    </nav>
  </header>
  <div class="simulation-strip">校园闲置 · 模拟交易，不扣真实款项</div>
  <main class="market-main">
    <PageState v-if="!session.ready" state="loading" title="正在连接校园集市" /><PageState
      v-else-if="session.startupError"
      state="error"
      title="连接未完成"
      :description="session.startupError"
      ><template #action
        ><AppButton @click="initializeSession">重试连接</AppButton></template
      ></PageState
    ><PageState
      v-else-if="route.meta.auth && !session.me"
      state="forbidden"
      title="登录后继续"
      description="登录后可发布闲置、查看订单和消息。"
      ><template #action
        ><RouterLink :to="{ path: '/login', query: { next: route.fullPath } }"
          >前往登录</RouterLink
        ></template
      ></PageState
    ><PageState
      v-else-if="Number(route.meta.rank || 0) > roleRank()"
      state="forbidden"
      title="暂无工作台权限"
      description="平台权限以服务端当前身份为准。"
    /><RouterView
      v-else
      :key="route.fullPath + ':' + session.epoch + ':' + number(session.me, 'id')"
    />
  </main>
  <footer class="market-footer">
    <img :src="logo" alt="华立转角" width="132" height="42" /><span>闲置有去处，同学有照应。</span
    ><RouterLink to="/support">客服 08:00—20:00 · 帮助与售后</RouterLink>
  </footer>
  <nav class="mobile-nav" aria-label="手机主导航">
    <RouterLink
      v-for="item in slots"
      :key="item.to"
      :to="item.to"
      :class="{ 'publish-slot': item.to === '/publish', current: navCurrent(item.to) }"
      ><span aria-hidden="true"><AppIcon :name="item.icon" :size="22" /></span>{{ item.label
      }}<b v-if="item.to === '/messages' && badge" class="badge">{{
        badge > 99 ? '99+' : badge
      }}</b></RouterLink
    >
  </nav>
  <AppDialog
    :open="!!session.recoveryCode"
    title="请私下保存账号恢复码"
    @close="session.recoveryCode = ''"
  >
    <p>恢复码仅本次显示。它可以重置账号密码，请妥善保管，不要发到群聊。</p>
    <code class="recovery-code">{{ session.recoveryCode }}</code>
    <AppButton
      @click="
        session.recoveryCode = '';
        !session.me && router.push('/login');
      "
      >我已保存</AppButton
    >
  </AppDialog>
</template>
