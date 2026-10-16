// Editing reuses the publish form; server CAS protects the original listing.
import { state as appState } from '../core/state.js';
import { context } from '../core/context.js';
import { defaults, cacheKey } from '../core/draft-config.js';
import { publishForm } from '../components/publish-form.js';
import { mountPublisher } from '../actions/publishing.js';
import { status } from '../core/drafts.js';
export async function editProduct(id){
  const deps=context(), dto=await deps.request('/product/edit?id='+Number(id));
  if(!deps.isVisible())return;
  let local=null;
  try{local=JSON.parse(localStorage.getItem(cacheKey(deps.user.id,id))||'null');}catch{}
  const cached=local?.dirty?local:null;
  const editor={deps,mode:'edit',productId:Number(id),id:'edit-'+id,version:cached?.version||dto.version,
    fields:{...defaults,...(cached?.fields||dto.fields)},photos:cached?.photos||dto.photos,
    queue:Promise.resolve(),uploads:new Set(),urls:new Set(),failed:new Set(cached?.failed_angles||[]),
    generations:{},localOK:true,conflict:!!cached && cached.version!==dto.version,touched:!!cached,timer:null,
    lastSaved:cached?'':JSON.stringify(dto.fields)};
  editor.generation=++appState.draftGeneration;
  appState.draftEditor=editor;
  deps.shell(publishForm(editor,deps));
  mountPublisher(editor);
  document.querySelector('.publish-heading h1').textContent='编辑商品';
  document.querySelector('.publish-submit button').textContent='保存商品修改';
  document.querySelector('[data-draft-copy]').hidden=true;
  status(editor,editor.conflict?'商品已更新；本机修改未覆盖服务器，请读取新版后核对':'未提交修改仅缓存在本机；保存后影响新订单，原订单快照保持不变',editor.conflict);
}
