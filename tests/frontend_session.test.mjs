import assert from 'node:assert/strict';
const storage=new Map();
globalThis.window={HUALI_STATIC_DEMO:false};
globalThis.sessionStorage={getItem:()=>null};
globalThis.localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
globalThis.document={querySelector:()=>null,querySelectorAll:()=>[]};
const {state}=await import('../web 7M/src/core/state.js');
const {submit}=await import('../web 7M/src/actions/publishing.js');
const {cacheKey}=await import('../web 7M/src/core/draft-config.js');
function editor(id,request,visible=()=>true){
 const fields={title:'旧草稿',photos:[]};
 return {id,version:1,fields,photos:[],failed:new Set(),uploads:new Set(),urls:new Set(),queue:Promise.resolve(),lastSaved:JSON.stringify(fields),
 deps:{user:{id:4},isCurrent:()=>true,isVisible:visible,request,toast(){},go(){throw new Error('old publisher navigated over the new page');}}};
}
let resolvePublish,entered;
const pending=new Promise(resolve=>{entered=resolve;});
const old=editor('old-id',()=>{entered();return new Promise(resolve=>{resolvePublish=resolve;});});
state.draftEditor=old;
const job=submit();await pending;
const next=editor('new-id',async()=>({}));state.draftEditor=next;
localStorage.setItem(cacheKey(4),JSON.stringify({id:'new-id',fields:{title:'新草稿'}}));
resolvePublish({id:77});await job;
assert.equal(state.draftEditor,next,'late publication must preserve newer editor');
assert.equal(JSON.parse(localStorage.getItem(cacheKey(4))).id,'new-id','late publication must preserve newer local cache');
let posted=false;
state.draftEditor=editor('left',async()=>{posted=true;},()=>false);
await assert.rejects(submit(),/页面|切换/);
assert.equal(posted,false,'leaving the form before uploads finish must stop publication');
console.log('Frontend late publication and navigation preserve newer draft and cache.');
