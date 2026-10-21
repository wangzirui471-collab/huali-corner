/** 仅启动本机 Vue 预览；API 代理指向隔离的新 FastAPI 端口。 */
import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api/v1': 'http://127.0.0.1:8001' },
  },
  test: {
    environment: 'happy-dom',
    // 控件库按浏览器方式预打包，避免 Node 的 CJS 默认导出破坏 async-validator。
    server: { deps: { inline: ['element-plus'] } },
    include: ['src/**/*.test.js'],
    clearMocks: true,
    restoreMocks: true,
  },
});
