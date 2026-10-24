/** 业务前端仅在开发或显式 trial 隔离构建启用；默认生产入口保持未上线状态。 */
import { createRouter, createWebHistory } from 'vue-router';
import { legacyDestination } from './navigation.js';
const businessEnabled = import.meta.env.DEV || import.meta.env.MODE === 'trial';
const previewEnabled = import.meta.env.DEV || import.meta.env.MODE === 'preview';
/** @type {import('vue-router').RouteRecordRaw[]} 仅登记实际已经存在的前端页面。 */
const routes = [];
if (businessEnabled)
  routes.push({
    path: '/',
    component: () => import('@/layouts/MarketLayout.vue'),
    children: [
      { path: '', component: () => import('@/features/catalog/HomePage.vue') },
      { path: 'login', component: () => import('@/features/identity/LoginPage.vue') },
      { path: 'products/:id(\\d+)', component: () => import('@/features/catalog/ProductPage.vue') },
      {
        path: 'publish',
        meta: { auth: true },
        component: () => import('@/features/catalog/PublishPage.vue'),
      },
      {
        path: 'favorites',
        meta: { auth: true },
        component: () => import('@/features/catalog/HomePage.vue'),
      },
      {
        path: 'my-products',
        meta: { auth: true },
        component: () => import('@/features/catalog/MyListingsPage.vue'),
      },
      {
        path: 'cart',
        meta: { auth: true },
        component: () => import('@/features/trade/CartPage.vue'),
      },
      {
        path: 'orders',
        meta: { auth: true },
        component: () => import('@/features/trade/OrdersPage.vue'),
      },
      {
        path: 'me/:section?',
        meta: { auth: true },
        component: () => import('@/features/identity/ProfilePage.vue'),
      },
      { path: 'users/:id(\\d+)', component: () => import('@/features/identity/ProfilePage.vue') },
      { path: 'community', component: () => import('@/features/community/CommunityPage.vue') },
      {
        path: 'forum/account',
        meta: { auth: true },
        component: () => import('@/features/community/CommunityPage.vue'),
      },
      { path: 'forum/:board?', component: () => import('@/features/community/CommunityPage.vue') },
      { path: 'posts/:id(\\d+)', component: () => import('@/features/community/PostPage.vue') },
      { path: 'wants/:id(\\d+)', component: () => import('@/features/community/PostPage.vue') },
      {
        path: 'friends',
        meta: { auth: true },
        component: () => import('@/features/community/FriendsPage.vue'),
      },
      {
        path: 'messages/:id?',
        meta: { auth: true },
        component: () => import('@/features/community/MessagesPage.vue'),
      },
      {
        path: 'support/:id?',
        meta: { auth: true },
        component: () => import('@/features/support/SupportPage.vue'),
      },
      {
        path: 'workspace/users/:id(\\d+)',
        meta: { auth: true, rank: 2 },
        component: () => import('@/features/workspace/DossierPage.vue'),
      },
      {
        path: 'workspace/:section?',
        meta: { auth: true, rank: 1 },
        component: () => import('@/features/workspace/WorkspacePage.vue'),
      },
      { path: ':pathMatch(.*)*', component: () => import('./MissingPage.vue') },
    ],
  });
if (previewEnabled)
  routes.push({ path: '/_dev/components', component: () => import('./ComponentGalleryPage.vue') });
if (!businessEnabled)
  routes.push({ path: '/:pathMatch(.*)*', component: () => import('./UnavailablePage.vue') });
export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, saved) {
    return saved || { top: 0 };
  },
});
/** 旧 hash 书签替换到本站地址，不污染浏览器返回栈。 */
router.beforeEach((to) => {
  const target = businessEnabled ? legacyDestination(to.hash) : null;
  if (!target) return true;
  const parsed = new URL(target, 'http://huali.invalid');
  return {
    path: parsed.pathname,
    query: { ...to.query, ...Object.fromEntries(parsed.searchParams) },
    replace: true,
  };
});
