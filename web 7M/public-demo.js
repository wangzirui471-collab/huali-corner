'use strict';
// Included only in exported preview HTML. No authentication or write endpoints.
window.HUALI_STATIC_DEMO=true;
window.hualiDemoApi=async function(path,data){
 if(data!==undefined)throw new Error('公开演示版不提交数据');
 if(!window.hualiDemoSnapshot)window.hualiDemoSnapshot=fetch('./demo-data.json').then(r=>{if(!r.ok)throw new Error('演示数据加载失败');return r.json();});
 const snapshot=await window.hualiDemoSnapshot,url=new URL(path,location.origin),query=url.searchParams;
 const product=id=>{const p=snapshot.products.find(p=>p.id===Number(id));if(!p)throw new Error('演示商品不存在');return p;};
 if(url.pathname==='/config')return snapshot.config;
 if(['/products','/products/search'].includes(url.pathname)){
  let rows=snapshot.products.filter(p=>(!query.get('category')||p.category===query.get('category'))&&(!query.get('seller')||p.seller_id===Number(query.get('seller'))));
  const q=(query.get('q')||'').toLowerCase();
  if(q)rows=rows.filter(p=>['title','description','isbn','publisher','major','edition'].map(k=>p[k]||'').join(' ').toLowerCase().includes(q));
  if(query.get('sort')==='price')rows.sort((a,b)=>(a.price+(a.delivery==='delivery'?a.delivery_fee:0))-(b.price+(b.delivery==='delivery'?b.delivery_fee:0)));
  const delivery=query.get('delivery')||'';
  if(delivery)rows=rows.filter(p=>p.delivery===delivery||p.delivery==='both');
  if(query.get('free'))rows=rows.filter(p=>p.price===0);
  const cost=p=>p.price+((p.delivery==='delivery'||delivery==='delivery')?p.delivery_fee:0);
  for(const k of ['college','major','course','edition','condition']){
    const value=query.get(k);if(value)rows=rows.filter(p=>value==='unknown'?(!p[k]||/待|未知|未核对/.test(p[k])):p[k]===value);
  }
  if(query.get('min_price'))rows=rows.filter(p=>cost(p)>=Number(query.get('min_price')));
  if(query.get('max_price'))rows=rows.filter(p=>cost(p)<=Number(query.get('max_price')));
  if(['price','price_asc','price_desc'].includes(query.get('sort')))rows.sort((a,b)=>(cost(a)-cost(b))*(query.get('sort')==='price_desc'?-1:1)||b.id-a.id);
  return url.pathname==='/products'?rows:{items:rows,next_cursor:null,has_more:false};
 }
 if(url.pathname==='/product')return product(query.get('id'));
 if(url.pathname==='/profile'){
  const user=snapshot.profiles[query.get('id')];if(!user)throw new Error('演示主页不存在');
  return {user,products:snapshot.products.filter(p=>p.seller_id===user.id)};
 }
 if(url.pathname==='/posts')return snapshot.posts;
 if(url.pathname==='/comments')return snapshot.comments[query.get('id')]||[];
 throw new Error('此功能仅在本地模拟版开放');
};
