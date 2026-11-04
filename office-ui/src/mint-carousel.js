import { createApp } from 'vue';
import { ElCarousel, ElCarouselItem, ElConfigProvider } from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/es/components/carousel/style/css';
import MintCarousel from './MintCarousel.vue';

/** 在现有首页里挂载轮播，返回供路由切换时调用的卸载函数。 */
export function mountMintCarousel(root, slides) {
  const app = createApp(MintCarousel, { slides });
  app.component('ElCarousel', ElCarousel);
  app.component('ElCarouselItem', ElCarouselItem);
  app.component('ElConfigProvider', ElConfigProvider);
  app.provide('mintLocale', zhCn);
  app.mount(root);
  return () => app.unmount();
}
