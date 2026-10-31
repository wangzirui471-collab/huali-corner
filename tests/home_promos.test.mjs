import test from 'node:test';
import assert from 'node:assert/strict';
let heroSlides, heroFallback, promoPanels, linkAttrs;
try { ({heroSlides,heroFallback,promoPanels,linkAttrs}=await import('../web 7M/src/components/home-promos.js')); }
catch(error){ if(error.code!=='ERR_MODULE_NOT_FOUND') throw error; }

test('six editorial slides each point at a real campus destination',()=>{
  assert.equal(promoPanels.length,2);
  for(const panel of promoPanels){
    assert.equal(panel.slides.length,3);
    assert.ok(panel.interval>=6000);
    for(const slide of panel.slides) assert.ok(slide.category||slide.route||slide.free);
  }
  const slides=heroSlides();
  assert.equal(slides.length,6);
  assert.equal(new Set(slides.map(slide=>slide.key)).size,6,'slide keys must be unique');
  for(const slide of slides){
    assert.ok(slide.title&&slide.eyebrow&&slide.description&&slide.cta);
    assert.ok(slide.tone&&slide.art&&slide.arrow);
    // 每张都必须真的能跳：分类 / 免费送 / 路由，三选一。
    assert.ok(slide.link.action||slide.link.go,`slide ${slide.key} has no destination`);
  }
  assert.deepEqual(slides.find(slide=>slide.title==='好物留在华立').link,{go:'community'});
  assert.deepEqual(slides.find(slide=>slide.title==='免费送，也有新故事').link,{action:'free-shelf'});
  assert.deepEqual(slides.find(slide=>slide.title==='教材不必买新的').link,{action:'market-shortcut',value:'books',q:''});
});

test('fallback carousel renders one window, six slides, six dots and no pause control',()=>{
  const html=heroFallback(heroSlides());
  assert.equal((html.match(/data-home-carousel=/g)||[]).length,1,'首页只留一条主视觉轮播');
  assert.equal((html.match(/data-promo-slide=/g)||[]).length,6);
  assert.equal((html.match(/data-action="home-slide"/g)||[]).length,6);
  // 每张幻灯片自带跳转，不再需要「读当前页再决定去哪」的第二个按钮。
  assert.doesNotMatch(html,/home-promo-open/);
  assert.doesNotMatch(html,/home-pause|暂停|自动播放|onmouseenter|onmouseover/);
  assert.equal((html.match(/<button class="hc-slide/g)||[]).length,6);
  assert.equal((html.match(/data-action="market-shortcut"/g)||[]).length,3);
  assert.equal((html.match(/data-action="free-shelf"/g)||[]).length,1);
  assert.equal((html.match(/data-go="/g)||[]).length,2);
  for(const title of ['教材不必买新的','好物留在华立']) assert.ok(html.includes(title));
});

test('linkAttrs only writes the attributes a destination actually needs',()=>{
  assert.equal(linkAttrs({action:'market-channel',value:'',q:''}),'data-action="market-channel" data-value="" data-q=""');
  assert.equal(linkAttrs({action:'free-shelf'}),'data-action="free-shelf"');
  assert.equal(linkAttrs({go:'publish'}),'data-go="publish"');
  assert.equal(linkAttrs({action:'market-shortcut',value:'living',q:'<灯>&'}),'data-action="market-shortcut" data-value="living" data-q="&lt;灯&gt;&amp;"');
});
