import { fileURLToPath, URL } from "node:url";
import vue from "../../../apps/web/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import { defineConfig } from "../../../apps/web/node_modules/vitest/dist/config.js";

/** 直接复用项目内已有依赖，不创建系统链接或安装其他全局环境。 */
const dependency = (name) =>
  fileURLToPath(
    new URL("../../../apps/web/node_modules/" + name, import.meta.url),
  );

/** 独立评审预览只监听本机，不配置业务代理，不改正式路由。 */
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [vue()],
  resolve: {
    alias: [
      {
        find: "@/features/community/CommunityPage.vue",
        replacement: fileURLToPath(
          new URL("./src/pages/CommunityReview.vue", import.meta.url),
        ),
      },
      {
        find: "@/features/trade/OrdersPage.vue",
        replacement: fileURLToPath(
          new URL("./src/pages/OrdersReview.vue", import.meta.url),
        ),
      },
      {
        find: "@/features/community/MessagesPage.vue",
        replacement: fileURLToPath(
          new URL("./src/pages/MessagesReview.vue", import.meta.url),
        ),
      },
      {
        find: /^vue-router$/,
        replacement: dependency("vue-router/dist/vue-router.mjs"),
      },
      {
        find: "@",
        replacement: fileURLToPath(
          new URL("../../../apps/web/src", import.meta.url),
        ),
      },
      {
        find: /^vue$/,
        replacement: dependency("vue/dist/vue.runtime.esm-bundler.js"),
      },
      {
        find: /^element-plus$/,
        replacement: dependency("element-plus/es/index.mjs"),
      },
      { find: "element-plus", replacement: dependency("element-plus") },
      {
        find: "@vue/test-utils",
        replacement: dependency(
          "@vue/test-utils/dist/vue-test-utils.esm-bundler.mjs",
        ),
      },
      { find: /^vitest$/, replacement: dependency("vitest/dist/index.js") },
    ],
  },
  server: {
    host: "127.0.0.1",
    port: 5198,
    strictPort: true,
    fs: { allow: [fileURLToPath(new URL("../../../", import.meta.url))] },
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.js"],
    server: { deps: { inline: ["element-plus"] } },
    clearMocks: true,
    restoreMocks: true,
  },
});
