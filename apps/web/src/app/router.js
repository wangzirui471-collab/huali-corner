/** 组件样板只在开发或明确的隔离 preview 构建中启用。 */
import { createRouter, createWebHistory } from 'vue-router';

const previewEnabled = import.meta.env.DEV || import.meta.env.MODE === 'preview';
/** @type {import('vue-router').RouteRecordRaw[]} 路由表仅登记实际已实现页面。 */
const routes = [{ path: '/:pathMatch(.*)*', component: () => import('./UnavailablePage.vue') }];
if (previewEnabled) {
  routes.unshift(
    { path: '/', redirect: '/_dev/components' },
    { path: '/_dev/components', component: () => import('./ComponentGalleryPage.vue') },
  );
}
export const router = createRouter({ history: createWebHistory(), routes });
