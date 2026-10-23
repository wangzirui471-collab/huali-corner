/** 构建仅在 L1 打开办公面板时加载的 Vue 岛，复用现有站点与登录态。 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: fileURLToPath(new URL('../web 7M/assets/office', import.meta.url)),
    emptyOutDir: false,
    lib: { entry: 'src/main.js', formats: ['es'], fileName: () => 'office-panel.js', cssFileName: 'office-panel' },
    sourcemap: false,
    minify: true
  },
  define: { 'process.env.NODE_ENV': '"production"' }
});
