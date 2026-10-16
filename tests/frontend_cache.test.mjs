import assert from 'node:assert/strict';
const storage=new Map();
globalThis.window={HUALI_STATIC_DEMO:false};
globalThis.sessionStorage={getItem:()=>null};
globalThis.localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
globalThis.FormData=class{constructor(form){this.form=form;}[Symbol.iterator](){return [['title',this.form.title]][Symbol.iterator]();}};
globalThis.fetch=async()=>({ok:true,blob:async()=>new Blob(['photo'])});
globalThis.FileReader=class{readAsDataURL(){this.result='data:image/png;base64,eA==';this.onload();}};
const {state}=await import('../web 7M/src/core/state.js');
const {cache,upload}=await import('../web 7M/src/core/drafts.js');
const {cacheKey}=await import('../web 7M/src/core/draft-config.js');
const slot={replaceChildren(){},isConnected:false},count={textContent:''};
let deliver,entered;
const began=new Promise(resolve=>{entered=resolve;});
function editor(id,generation){return {id,generation,touched:true,version:0,fields:{title:id},photos:[],failed:new Set(),generations:{},urls:new Set(),lastSaved:'',form:{title:id,querySelector:selector=>selector==='.photo-count'?count:slot},deps:{user:{id:4},session:'test',isCurrent:()=>true,request:()=>{entered();return new Promise(resolve=>{deliver=resolve;});}}};}
const old=editor('draft-a',1);state.draftGeneration=1;state.draftEditor=old;
const job=upload(old,{size:1},'front');await began;
const newer=editor('draft-b',2);state.draftGeneration=2;state.draftEditor=newer;
// No form contents are needed for this unsynced recovery snapshot.
newer.form=null;cache(newer);
assert.equal(JSON.parse(localStorage.getItem(cacheKey(4))).id,'draft-b');
state.draftEditor=null; // B left the page after its server save failed.
deliver({id:'uploaded-a',angle:'front',url:'/media/uploaded-a'});await job;
assert.equal(JSON.parse(localStorage.getItem(cacheKey(4))).id,'draft-b','late upload A must not replace suspended B recovery cache');
await new Promise(setImmediate);for(const url of old.urls)URL.revokeObjectURL(url);
console.log('Frontend late upload preserves the newer suspended unsynced draft cache.');
