import test from 'node:test';
import assert from 'node:assert/strict';
let homePromos, promoPanels;
try { ({homePromos,promoPanels}=await import('../web 7M/src/components/home-promos.js')); }
catch(error){ if(error.code!=='ERR_MODULE_NOT_FOUND') throw error; }
test('two compact windows each contain three real campus destinations, without pause controls',()=>{
  assert.equal(typeof homePromos,'function','missing dual carousel component');
  assert.equal(promoPanels.length,2);
  for(const panel of promoPanels){
    assert.equal(panel.slides.length,3);
    assert.ok(panel.interval>=6000);
    for(const slide of panel.slides) assert.ok(slide.category||slide.route||slide.free);
  }
  const html=homePromos();
  assert.equal((html.match(/data-home-carousel=/g)||[]).length,2);
  assert.equal((html.match(/data-promo-slide=/g)||[]).length,6);
  assert.equal((html.match(/data-action="home-slide"/g)||[]).length,6);
  assert.doesNotMatch(html,/home-pause|暂停|自动播放|onmouseenter|onmouseover/);
  for(const title of ['教材不必买新的','好物留在华立']) assert.ok(html.includes(title));
});
