import { state as appState } from '../core/state.js';
import { context } from '../core/context.js';
import { cacheKey, defaults, uid } from '../core/draft-config.js';
import { publishForm } from '../components/publish-form.js';
import { changed, status } from '../core/drafts.js';
import { mountPublisher } from '../actions/publishing.js';
export async function publish(draftId) {
    const deps=context();
    let cached = null;
    try { cached = JSON.parse(localStorage.getItem(cacheKey(deps.user.id)) || 'null'); } catch {}
    let draft = null;
    let restoredLocal = false;
    let reopenedConflict = false;
    const requested = draftId && draftId !== 'new' ? draftId : (!draftId ? cached?.id : null);
    if (requested) {
      try { draft = await deps.request('/draft?id=' + encodeURIComponent(requested)); }
      catch (error) {
        if (draftId && draftId !== 'new') throw error;
        if (cached?.version === 0) {
          draft = { id: cached.id, version: 0, fields: cached.fields, photos: cached.photos || [] };
          restoredLocal = true;
        }
      }
    }
    if (draft && cached?.id === draft.id && cached.dirty) {
      reopenedConflict = cached.version !== draft.version;
      if (reopenedConflict) draft.version = cached.version;
      draft.fields = cached.fields;
      draft.photos = cached.photos || draft.photos;
      restoredLocal = true;
    }
    const state = {
      deps, id: draft?.id || uid(), version: draft?.version || 0,
      fields: { ...defaults, ...(draft?.fields || {}) }, photos: draft?.photos || [],
      source: draft?.source_product_id, queue: Promise.resolve(), uploads: new Set(), urls: new Set(),
      copyFrom: cached?.id === draft?.id && !draft?.version ? cached?.copy_from_id : null,
      failed: new Set(cached?.id === draft?.id ? cached?.failed_angles || [] : []), generations: {}, localOK: true, conflict: reopenedConflict, timer: null,
      touched: !!draft,
    };
    if (draft?.fields?.photos?.length && state.photos.length !== draft.fields.photos.length) {
      state.photos = draft.fields.photos.map(id => state.photos.find(item => item.id === id)).filter(Boolean);
    }
    if(!deps.isVisible())return;
    state.generation=++appState.draftGeneration;
    appState.draftEditor = state;
    const value = state.fields;
    if(!value.college)value.college=deps.user.college||'';
    if(!value.major)value.major=deps.user.major||'';
    const buildings = deps.config.buildings || [];
    if (!value.building) value.building = buildings[0] || '';
    state.lastSaved = draft && !restoredLocal ? JSON.stringify({ ...state.fields, photos: state.photos.map(photo => photo.id) }) : '';
    deps.shell(publishForm(state,deps,{draft,restoredLocal}));
    mountPublisher(state);
    if (restoredLocal) changed(state);
    if (state.conflict) status(state, '版本冲突：已保留本机未同步修改，可读取新版或另存一份', true);
    else if (state.failed.size) status(state, '草稿已恢复');
  }
