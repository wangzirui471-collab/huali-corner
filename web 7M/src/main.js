/** Vue 应用唯一入口，保留原站页面容器、AI 和业务模块。 */
import {createApp} from 'vue';
import App from './framework/App.vue';
import LegacyPage from './framework/LegacyPage.vue';
import {pinia} from './framework/store.js';
import {createSiteRouter} from './framework/router.js';
import {configureNavigation} from './core/nav.js';

const router = createSiteRouter(LegacyPage);
const app = createApp(App);
configureNavigation(router);
app.use(pinia);
app.use(router);
await router.isReady();
app.mount('#huali-root');

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    app.unmount();
    router.options.history.destroy();
  });
}
