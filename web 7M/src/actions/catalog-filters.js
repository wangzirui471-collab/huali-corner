import { state } from '../core/state.js';
import { loadFeed, emptyFilter, queryFilters } from '../core/catalog-feed.js';
import { yuanToCents } from '../core/money.js';
import { filterForm } from '../components/catalog-filters.js';
import { card } from '../components/product-card.js';
import { modal, closeModal } from '../core/shell.js';
import { go } from '../core/nav.js';
import { toast } from '../core/dom.js';
export const clicks={
 'open-filter':()=>modal(filterForm()),
 'clear-filters':()=>{state.filter=emptyFilter();state.freeShelf=false;closeModal();go('home');},
 'share-filters':async()=>{const url=new URL(location.href);url.hash='home?'+new URLSearchParams(queryFilters());await navigator.clipboard.writeText(url.href);toast('已复制当前筛选链接');},
 'more-products':async button=>{button.disabled=true;const feed=await loadFeed(true);document.querySelector('.product-grid').innerHTML=feed.items.map(card).join('');if(!feed.hasMore)button.remove();else button.disabled=false;}
};
export const submits={'catalog-filter-form':({d})=>{
 const f={q:state.filter.q,category:d.category,sort:d.sort};
 for(const k of ['college','condition','delivery',...(!d.category||d.category==='books'?['major','course','edition']:[])])if(d[k]?.trim())f[k]=d[k].trim();
 for(const k of ['min_price','max_price'])if(d[k]?.trim())f[k]=String(yuanToCents(d[k]));
 if(f.min_price&&f.max_price&&Number(f.min_price)>Number(f.max_price))throw new Error('最低价不能高于最高价');
 state.filter=f;state.freeShelf=false;closeModal();go('home');
}};
