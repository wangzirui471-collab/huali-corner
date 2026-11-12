/** 路由只负责匹配与历史；原页面继续负责权限、业务和错误兜底。 */
import {createRouter, createWebHashHistory} from 'vue-router';

export const SITE_ROUTES = [
  'home', 'favorites', 'product', 'publish', 'cart', 'orders', 'listings',
  'community', 'forum', 'forum-post', 'forum-want', 'forum-compose',
  'messages', 'profile', 'me', 'support', 'staff', 'admin', 'dossier',
  'credit', 'ticket',
];

/** 将所有原页面绑定到稳定适配组件，允许在 Node 中注入内存历史测试。 */
export function createSiteRouter(component, history = createWebHashHistory()) {
  return createRouter({
    history,
    routes: [
      {path: '/', redirect: '/home'},
      ...SITE_ROUTES.map(name => ({path: '/' + name + '/:id?', name, component})),
      {path: '/:pathMatch(.*)*', redirect: '/home'},
    ],
  });
}
