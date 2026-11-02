import test from 'node:test';
import assert from 'node:assert/strict';
let homePromos, promoPanels;
try { ({homePromos,promoPanels}=await import('../web 7M/src/components/home-promos.js')); }
catch(error){ if(error.code!=='ERR_MODULE_NOT_FOUND') throw error; }

test('one carousel window with three keyword-only slides',()=>{
  assert.equal(typeof homePromos,'function');
  assert.equal(promoPanels.length,1,'首页只留一条主视觉轮播');
  const [panel]=promoPanels;
  assert.equal(panel.slides.length,3);
  assert.ok(panel.interval>=6000);
  for(const slide of panel.slides){
    // 每张都必须「分类 + 关键词」：只给分类就等于又造了一个频道行入口。
    assert.ok(slide.category,'slide needs a category');
    assert.ok(slide.q,'slide needs a keyword, otherwise it duplicates the channel row');
    assert.ok(!slide.route && !slide.free,'专题卡不再跳页面，避免与顶栏、频道行重复');
    assert.ok(slide.title&&slide.eyebrow&&slide.description&&slide.cta);
  }
  assert.equal(new Set(panel.slides.map(slide=>`${slide.category}:${slide.q}`)).size,3,'三张卡必须是三个不同去处');
});

test('rendered carousel keeps one window, three slides, three dots and no pause control',()=>{
  const html=homePromos();
  assert.equal((html.match(/data-home-carousel=/g)||[]).length,1);
  assert.equal((html.match(/data-promo-slide=/g)||[]).length,3);
  assert.equal((html.match(/data-action="home-slide"/g)||[]).length,3);
  assert.equal((html.match(/data-action="home-promo-open"/g)||[]).length,1,'一张窗口一个可点区');
  assert.doesNotMatch(html,/home-pause|暂停|自动播放|onmouseenter|onmouseover/);
  // 关键词要真的写进 DOM，home-promo-open 才带着 q 去搜，而不是退回分类。
  for(const q of ['灯','收纳','凳']) assert.ok(html.includes(`data-q="${q}"`),`missing keyword ${q}`);
});
