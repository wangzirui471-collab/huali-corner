import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { homeHero, heroSlides } = await import('../web 7M/src/components/home-hero.js');

// 验证旧专题入口在轮播加载失败时仍有可用的静态链接。
test('mint home keeps topic destinations available before the carousel mounts', () => {
  const html = homeHero();
  assert.ok(html.includes('data-mint-carousel'));
  for (const go of ['home/living', 'home/books', 'home/free', 'forum/wants', 'publish']) {
    assert.ok(html.includes(`data-go="${go}"`), go);
  }
  assert.deepEqual(heroSlides.map(slide => slide.go), ['publish', 'home/books', 'home/living', 'forum/wants']);
});

test('mint carousel drops text tabs but keeps arrows, progress and autoplay', () => {
  const html = homeHero();
  // 四个文字 tab（校园/教材/宿舍/求购）已移除。
  assert.doesNotMatch(html, /mint-carousel-pages|data-slide-index/);
  // 左右箭头和 1 / 4 进度提示保留。
  assert.equal((html.match(/data-slide-step="-1"/g) || []).length, 1);
  assert.equal((html.match(/data-slide-step="1"/g) || []).length, 1);
  assert.match(html, /mint-carousel-status[^>]*>1 \/ 4</);
  // 每秒自动切换，且节点离开文档后自行清理定时器。
  const src = fs.readFileSync(path.join(ROOT, 'web 7M', 'src', 'components', 'home-hero.js'), 'utf8');
  assert.match(src, /setInterval\(/);
  assert.match(src, /show\(current \+ 1\)/);
  assert.match(src, /\},\s*1000\s*\)/);
  assert.match(src, /!carousel\.isConnected.*clearInterval\(timer\)/s);
});

test('homes no longer ship the 小转推荐 rail', () => {
  const src = path.join(ROOT, 'web 7M', 'src');
  assert.equal(fs.existsSync(path.join(src, 'components', 'rec-rail.js')), false, 'rec-rail 组件应已删除');
  assert.equal(fs.existsSync(path.join(src, 'components', 'home-promos.js')), false, '旧单窗口专题组件应已删除');
  const home = fs.readFileSync(path.join(src, 'pages', 'home.js'), 'utf8');
  assert.doesNotMatch(home, /rec=1|recRail|小转/);
});
