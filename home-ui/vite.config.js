/** 构建只在逛逛页挂载的 Vue 岛；商品流、路由和业务状态仍归原生站点。 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: fileURLToPath(new URL('../web 7M/assets/home', import.meta.url)),
    emptyOutDir: false,
    lib: { entry: 'src/main.js', formats: ['es'], fileName: () => 'home-island.js', cssFileName: 'home-island' },
    sourcemap: false,
    minify: true
  },
  define: { 'process.env.NODE_ENV': '"production"' }
});
