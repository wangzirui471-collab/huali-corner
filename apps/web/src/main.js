/** JavaScript 入口：统一装配 Vue、路由和 Pinia，Element Plus 按组件显式引入。 */
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import 'element-plus/theme-chalk/base.css';
import 'element-plus/theme-chalk/el-icon.css';
import App from './app/App.vue';
import { router } from './app/router';
import './shared/design-tokens/tokens.css';
import './app/base.css';
import './shared/ui/element-plus.css';

createApp(App).use(createPinia()).use(router).mount('#app');
