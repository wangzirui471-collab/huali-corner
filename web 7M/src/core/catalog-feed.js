import { state } from './state.js';
import { api } from './http.js';
export const emptyFilter=()=>({category:'',q:'',sort:''});
export function queryFilters(){return {...state.filter,...(state.freeShelf?{free:'1'}:{})};}
export async function loadFeed(more=false){
 const query=queryFilters(),key=JSON.stringify(query),previous=state.feed;
 const result=await api('/products/search?'+new URLSearchParams({...query,...(more&&previous?.cursor?{cursor:previous.cursor}:{})}));
 const seen=new Set(more&&previous?.key===key?previous.items.map(x=>x.id):[]);
 const items=more&&previous?.key===key?[...previous.items]:[];
 for(const item of result.items)if(!seen.has(item.id)){items.push(item);seen.add(item.id);}
 state.feed={key,items,cursor:result.next_cursor,hasMore:result.has_more};
 return state.feed;
}
