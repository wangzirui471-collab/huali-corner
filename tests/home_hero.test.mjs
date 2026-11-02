import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let homeHero, heroPanels;
try { ({ homeHero, heroPanels } = await import('../web 7M/src/components/home-hero.js')); }
catch (error) { if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error; }

test('two hero cards, three slides each, every slide has its own destination', () => {
  assert.equal(typeof homeHero, 'function');
  assert.equal(heroPanels.length, 2, '首页保留两张主视觉卡：教材 / 宿舍好物');
  assert.deepEqual(heroPanels.map(panel => panel.key), ['books', 'living']);
  for (const panel of heroPanels) {
    assert.equal(panel.slides.length, 3);
    assert.ok(panel.interval >= 6000);
    for (const slide of panel.slides) {
      assert.ok(slide.title && slide.eyebrow && slide.description && slide.cta);
      // 每个 slide 必须自带去处：旧版三个入口都落回同一个商品流，点哪个都一样。
      assert.ok(slide.go, 'slide needs its own destination');
      assert.match(slide.go, /^(home\/|forum\/|publish$)/, slide.go);
    }
    // 一张卡内部至少两个不同去处，避免三张 slide 只是换文案。
    assert.ok(new Set(panel.slides.map(slide => slide.go)).size >= 2);
  }
  // 两张卡的去处必须不同，否则又变成「点什么都是同一个页面」。
  assert.notEqual(heroPanels[0].slides[0].go, heroPanels[1].slides[0].go);
});

test('rendered hero keeps carousel hooks, one clickable card each, no rec rail', () => {
  const html = homeHero();
  assert.equal((html.match(/data-home-carousel=/g) || []).length, 2);
  assert.equal((html.match(/data-promo-slide=/g) || []).length, 6);
  assert.equal((html.match(/data-action="home-slide"/g) || []).length, 6);
  assert.equal((html.match(/data-action="home-promo-open"/g) || []).length, 2, '一张卡一个可点区');
  assert.equal((html.match(/data-go="/g) || []).length, 6, '每张 slide 都带自己的地址');
  assert.doesNotMatch(html, /rec-rail|小转|为你推荐|XIAOZHUAN/);
  assert.doesNotMatch(html, /onmouseenter|onmouseover|自动播放/);
});

test('homes no longer ship the 小转推荐 rail', () => {
  const src = path.join(ROOT, 'web 7M', 'src');
  assert.equal(fs.existsSync(path.join(src, 'components', 'rec-rail.js')), false, 'rec-rail 组件应已删除');
  assert.equal(fs.existsSync(path.join(src, 'components', 'home-promos.js')), false, '旧单窗口专题组件应已删除');
  const home = fs.readFileSync(path.join(src, 'pages', 'home.js'), 'utf8');
  assert.doesNotMatch(home, /rec=1|recRail|小转/);
});
