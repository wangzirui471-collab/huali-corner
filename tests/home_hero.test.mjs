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

test('homes no longer ship the 小转推荐 rail', () => {
  const src = path.join(ROOT, 'web 7M', 'src');
  assert.equal(fs.existsSync(path.join(src, 'components', 'rec-rail.js')), false, 'rec-rail 组件应已删除');
  assert.equal(fs.existsSync(path.join(src, 'components', 'home-promos.js')), false, '旧单窗口专题组件应已删除');
  const home = fs.readFileSync(path.join(src, 'pages', 'home.js'), 'utf8');
  assert.doesNotMatch(home, /rec=1|recRail|小转/);
});
