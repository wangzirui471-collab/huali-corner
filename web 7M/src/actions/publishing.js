import { state as appState } from '../core/state.js';
import { fields, status, cache, save, changed, drawPhotos, upload, clearLocal } from '../core/drafts.js';
import { uid } from '../core/draft-config.js';
export function mountPublisher(state){const deps=state.deps;state.form = document.getElementById('publish-form');
    drawPhotos(state);
    state.form.addEventListener('input', event => { if (event.target.type !== 'file') changed(state); });
    state.form.addEventListener('change', event => {
      if (event.target.type !== 'file') { changed(state); return; }
      state.touched = true;
      const angle=event.target.name, files=[...event.target.files];
      state.failed.add(angle);cache(state);
      const promise=(async()=>{for(const file of files)await upload(state,file,angle);})();
      state.uploads.add(promise);status(state,'图片上传中，请勿关闭页面');
      promise.catch(error=>{state.failed.add(angle);cache(state);status(state,error.message+'；请重新选择该照片');})
        .finally(()=>{state.uploads.delete(promise);if(!state.failed.size)save(state).catch(()=>{});});
    });
    state.form.querySelector('[data-draft-save]').onclick = () => { state.touched = true; save(state).catch(error => deps.toast(error.message)); };
    state.form.querySelector('[data-draft-reload]').onclick = async () => {
      if (!confirm('读取服务器新版会替换当前未同步内容。需要保留时请先选择另存一份。')) return;
      clearLocal(deps.user.id,state.productId);
      state.conflict = true;
      appState.draftEditor = null;
      await deps.render().catch(error => deps.toast(error.message));
    };
    state.form.querySelector('[data-draft-copy]').onclick = async () => {
      state.copyFrom = state.id; state.id = uid(); state.version = 0; state.conflict = false; state.lastSaved = '';
      await save(state).catch(error => deps.toast(error.message));
    };
}
export async function submit() {
    const state = appState.draftEditor;
    if (!state?.deps.isCurrent()) throw new Error('请重新登录后继续');
    state.touched = true;
    await Promise.allSettled([...state.uploads]);
    if (state.failed.size) throw new Error('有照片未上传完成，请重新选择后发布');
    await save(state);
    if(appState.draftEditor!==state || !state.deps.isVisible())throw new Error('页面已切换，草稿保留，请重新打开后发布');
    if(state.conflict)throw new Error('商品或草稿有新版，请先读取新版核对');
    const product = state.mode==='edit'?await state.deps.request('/product/edit',{id:state.productId,version:state.version,fields:fields(state)}):await state.deps.request('/draft/publish', { id: state.id, version: state.version });
    clearLocal(state.deps.user.id,state.productId,state.id);
    for (const url of state.urls) URL.revokeObjectURL(url);
    state.deps.toast('发布成功，草稿已关闭');
    if(state.deps.isVisible() && !appState.draftEditor)state.deps.go('product/' + product.id);
  }
export const submits={'publish-form':submit};

import { context } from '../core/context.js';
import { cacheKey } from '../core/draft-config.js';
export const clicks={'delete-draft':async button=>{const deps=context();if(!confirm('确认删除这份草稿？'))return;const id=button.dataset.draftId;await deps.request('/draft/delete',{id});try{const cached=JSON.parse(localStorage.getItem(cacheKey(deps.user.id))||'null');if(cached?.id===id)clearLocal(deps.user.id);}catch{}await deps.render();}};
