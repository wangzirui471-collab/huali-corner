/** 当前网页框架构建：编译 Vue 入口，原样保留样式、图片和办公/宠物静态包。 */
import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const root = fileURLToPath(new URL('.', import.meta.url));
const stylesheetTags = new Map();

/** 留住现有样式链接，避免 CSS 合并改变层叠顺序和已有资源地址。 */
function preserveStyles() {
  return [{
    name: 'huali-preserve-static-styles',
    /** 开发时同样按原字节提供链接样式，避免 PostCSS 改变浏览器容错行为。 */
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url, 'http://local.invalid');
        if (!url.pathname.endsWith('.css') || url.searchParams.has('import')) return next();
        const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
        if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next();
        res.setHeader('Content-Type', 'text/css; charset=utf-8');
        fs.createReadStream(file).pipe(res);
      });
    },
    transformIndexHtml:
      {order: 'pre', handler(html) {
        stylesheetTags.clear();
        return html.replace(/<link\b[^>]*rel="stylesheet"[^>]*>/g, tag => {
          const marker = '<!--huali-style-' + stylesheetTags.size + '-->';
          stylesheetTags.set(marker, tag);
          return marker;
        });
      }},
    /** 仅复制公开资源，绝不把 package、依赖、源码和配置当成网站文件发布。 */
    writeBundle(options) {
      const out = path.resolve(options.dir || path.join(root, 'dist'));
      for (const item of fs.readdirSync(root, {withFileTypes: true})) {
        if (item.name === 'assets' || item.name === 'miniprogram' || item.name.endsWith('.css')) {
          fs.cpSync(path.join(root, item.name), path.join(out, item.name), {
            recursive: true,
            filter: source => path.basename(source) !== 'package.json',
          });
        }
      }
      const css = 'src/components/product-moderation.css';
      fs.mkdirSync(path.dirname(path.join(out, css)), {recursive: true});
      fs.copyFileSync(path.join(root, css), path.join(out, css));
    },
  }, {
    name: 'huali-restore-static-styles',
    transformIndexHtml: {order: 'post', handler(html) {
      for (const [marker, tag] of stylesheetTags) html = html.replace(marker, tag);
      return html;
    }},
  }];
}

/** 开发代理只允许本机服务；不读取旧 remote:true Worker 配置。 */
function localBackend() {
  const target = process.env.HUALI_DEV_API_ORIGIN || 'http://127.0.0.1:8081';
  const url = new URL(target);
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) {
    throw new Error('HUALI_DEV_API_ORIGIN 仅允许本机 HTTP 服务');
  }
  return target;
}

export default defineConfig({
  root,
  publicDir: false,
  plugins: [vue(), ...preserveStyles()],
  build: {
    outDir: 'dist', target: ['es2022', 'safari16.4'], assetsDir: 'assets/framework', sourcemap: false,
    rolldownOptions: {output: {
      /** 既有图片保持原地址与字节，只有新编译的脚本使用内容摘要文件名。 */
      assetFileNames(asset) {
        const original = asset.originalFileNames?.[0]?.replaceAll('\\', '/');
        return original?.startsWith('assets/') ? original : 'assets/framework/[name]-[hash][extname]';
      },
    }},
  },
  server: {proxy: {'/api': {target: localBackend()}, '/media': {target: localBackend()}}},
});
