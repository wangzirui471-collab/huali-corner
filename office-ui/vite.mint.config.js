/** 将首页轮播独立打包，路由进入逛逛时才加载脚本。 */
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: fileURLToPath(new URL('../web 7M/assets/home-mint/', import.meta.url)),
    emptyOutDir: false,
    lib: { entry: 'src/mint-carousel.js', formats: ['es'], fileName: () => 'carousel-market.js', cssFileName: 'carousel' },
  },
  define: { 'process.env.NODE_ENV': '"production"' }
});
