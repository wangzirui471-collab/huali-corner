import test from 'node:test';
import assert from 'node:assert/strict';
const moduleURL = new URL('../web 7M/src/core/product-feed.js', import.meta.url);
let createProductFeed;
try { ({createProductFeed} = await import(moduleURL)); } catch (error) {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
}
test('pagination appends unique products and stops at the final page', async () => {
  assert.equal(typeof createProductFeed, 'function', 'missing product feed controller');
  const pages=[];
  const feed=createProductFeed({initial:[{id:1},{id:2}],size:2,fetchPage:async page=>{
    pages.push(page); return page===2 ? [{id:2},{id:3}] : [{id:4}];
  }});
  assert.deepEqual((await feed.next()).map(p=>p.id),[3]);
  assert.deepEqual((await feed.next()).map(p=>p.id),[4]);
  assert.equal(feed.hasMore,false);
  assert.deepEqual(await feed.next(),[]);
  assert.deepEqual(pages,[2,3]);
});
test('duplicate triggers do not double-fetch and a failed page retries without advancing', async () => {
  assert.equal(typeof createProductFeed, 'function', 'missing product feed controller');
  let release, calls=0;
  const feed=createProductFeed({initial:[{id:1}],size:1,fetchPage:async page=>{
    assert.equal(page,2); calls++;
    if(calls===1) return new Promise((_,reject)=>{ release=()=>reject(new Error('offline')); });
    return [{id:2}];
  }});
  const first=feed.next();
  assert.deepEqual(await feed.next(),[]);
  release(); await assert.rejects(first,/offline/);
  assert.equal(feed.hasMore,true);
  assert.deepEqual((await feed.next()).map(p=>p.id),[2]);
  assert.equal(calls,2);
});
test('disposed feed ignores a late response and cannot fetch again', async () => {
  assert.equal(typeof createProductFeed, 'function', 'missing product feed controller');
  let release;
  const feed=createProductFeed({initial:[{id:1}],size:1,fetchPage:()=>new Promise(resolve=>{release=resolve;})});
  const request=feed.next(); feed.dispose(); release([{id:2}]);
  assert.deepEqual(await request,[]);
  assert.deepEqual(await feed.next(),[]);
  assert.equal(feed.hasMore,false);
});

globalThis.window={HUALI_STATIC_DEMO:false};
globalThis.sessionStorage={getItem:()=>null};
globalThis.localStorage=globalThis.sessionStorage;
const {state}=await import('../web 7M/src/core/state.js');
const {card}=await import('../web 7M/src/components/product-card.js');
const product={id:1,seller_id:7,status:'available',category:'books',title:'教材',price:1200,original_price:3000,photos:[{url:'/media/test'}],nickname:'同学',region:'图书馆',delivery:'pickup',edition:'第二版'};
for(const role of ['user','support','admin','developer']) test(`public card has no delist action for ${role}; favorite and product links remain`,()=>{
  state.me={id:7,role}; const html=card(product);
  assert.doesNotMatch(html,/data-action="(?:delist|moderate-product)"/);
  assert.match(html,/data-action="favorite"/);
  assert.match(html,/data-go="product\/1"/);
});
