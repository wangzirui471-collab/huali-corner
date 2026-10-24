/** 仅启动本机 Vue 预览；API 代理指向隔离的新 FastAPI 端口。 */
import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';
import { localBackend } from './src/app/navigation.js';
const legacyOrigin = localBackend(process.env.HUALI_LEGACY_ORIGIN || 'http://127.0.0.1:8081');
// 保留浏览器 Host 与 Origin 的对应关系，由旧服务继续校验同源写入。
const proxy = {
  '/api/v1': 'http://127.0.0.1:8001',
  '/api': { target: legacyOrigin, changeOrigin: false },
  '/media': { target: legacyOrigin, changeOrigin: false },
};

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy,
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  test: {
    environment: 'happy-dom',
    // 控件库按浏览器方式预打包，避免 Node 的 CJS 默认导出破坏 async-validator。
    server: { deps: { inline: ['element-plus'] } },
    include: ['src/**/*.test.js'],
    clearMocks: true,
    restoreMocks: true,
  },
});
