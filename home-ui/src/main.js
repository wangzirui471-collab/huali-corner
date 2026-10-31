/** 将 Element Plus 主视觉岛挂到原生首页容器；数据、路由和业务操作仍由原生站点负责。 */
import { createApp } from 'vue';
import HomeChrome from './HomeChrome.vue';
// 只引入轮播与其依赖的基础样式，避免把整套组件库压进首屏。
import 'element-plus/es/components/carousel/style/css.mjs';

/** 挂载主视觉岛，返回卸载句柄供路由释放。 */
export function mountHomeChrome(root, props){
  const app = createApp(HomeChrome, props);
  app.mount(root);
  return { unmount(){ app.unmount(); } };
}
