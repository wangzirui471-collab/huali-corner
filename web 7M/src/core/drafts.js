import { state as appState } from './state.js';
import { cacheKey } from './draft-config.js';
export function fields(state) {
    const result = { ...state.fields };
    if (state.form) {
      for (const [name, value] of new FormData(state.form)) {
        if (typeof value === 'string') result[name] = value;
      }
    }
    result.photos = state.photos.map(photo => photo.id);
    return result;
  }

export function status(state, message, conflict = false) {
    if (state.form) {
      state.form.querySelector('[data-testid=draft-status]').textContent = message + (state.failed?.size ? '；有照片未上传完成，请重新选择：' + [...state.failed].map(angle => ({front:'正面',side:'侧面',top:'顶部',extra:'补图'}[angle] || angle)).join('、') : '');
      state.form.querySelector('.draft-conflict').hidden = !conflict;
    }
  }

export function cache(state) {
    if (state.generation !== appState.draftGeneration || !state.touched || !state.deps.isCurrent() || (appState.draftEditor && appState.draftEditor !== state)) return;
    try {
      localStorage.setItem(cacheKey(state.deps.user.id,state.productId), JSON.stringify({
        id: state.id, version: state.version, fields: fields(state),
        photos: state.photos.map(photo => ({ id: photo.id, angle: photo.angle, url: photo.url })),
        copy_from_id: state.copyFrom || null,
        failed_angles: [...state.failed],
        updated_at: Date.now(), dirty: state.lastSaved !== JSON.stringify(fields(state)),
      }));
      state.localOK = true;
    } catch {
      state.localOK = false;
      status(state, '本机存储不可用，正在尝试保存到服务器');
    }
  }

export function save(state) {
    clearTimeout(state.timer);
    if(state.mode==='edit'){cache(state);status(state,state.localOK?'修改已缓存在本机，点击保存商品修改后提交':'本机保存失败，请勿关闭页面');return Promise.resolve();}
    state.queue = state.queue.catch(() => {}).then(async () => {
      if (!state.deps.isCurrent()) return;
      if (!state.touched && !state.version) return;
      if (state.conflict) throw new Error('草稿版本冲突，请读取新版或另存一份');
      const snapshot = fields(state);
      const serialized = JSON.stringify(snapshot);
      if (serialized === state.lastSaved && state.version) return;
      status(state, state.uploads.size ? '图片上传中，文字保存中…' : '保存中…');
      try {
        const result = await state.deps.request('/draft', {
          id: state.id, version: state.version, fields: snapshot,
          ...(state.copyFrom && !state.version ? { copy_from_id: state.copyFrom } : {}),
        });
        if (!state.deps.isCurrent()) return;
        state.version = result.version;
        state.copyFrom = null;
        state.lastSaved = serialized;
        cache(state);
        status(state, state.uploads.size ? '图片上传中，请勿关闭页面' : `已保存于 ${new Date().toLocaleTimeString()}${state.localOK ? '' : '（本机缓存不可用）'}`);
      } catch (error) {
        state.conflict = error.message.includes('另一窗口') || error.message.includes('版本');
        status(state, state.conflict ? '版本冲突：未覆盖服务器新版' : '同步失败；本机保存状态见提示，联网后请重试', state.conflict);
        throw error;
      }
    });
    return state.queue;
  }

export function changed(state) {
    if (!state.deps.isCurrent()) return;
    state.touched = true;
    state.fields = fields(state);
    cache(state);
    if (!state.conflict) status(state, state.localOK ? '已在本机保存，等待同步…' : '本机未能保存，等待服务器同步…');
    clearTimeout(state.timer);
    state.timer = setTimeout(() => { save(state).catch(() => {}); }, 2000);
    const isBook = state.fields.category === 'books';
    state.form.querySelector('.book-fields').hidden = !isBook;
    state.form.querySelector('.delivery-fee').hidden = state.fields.delivery === 'pickup';
    if (state.fields.missing?.includes('有缺页') || state.fields.accessories?.includes('附件缺失')) {
      state.form.querySelector('details').open = true;
      state.form.querySelector('[name=description]').placeholder = '请说明缺页位置或缺失附件';
    }
  }

export async function preview(state, photo) {
    if (photo.preview) return photo.preview;
    const response = await fetch(photo.url, { headers: { Authorization: 'Bearer ' + state.deps.session } });
    if (!response.ok) throw new Error('已保存照片暂时无法读取，请重试');
    const url = URL.createObjectURL(await response.blob());
    state.urls.add(url);
    photo.preview = url;
    return url;
  }

export function drawPhotos(state) {
    for (const angle of ['front', 'side', 'top']) {
      const slot = state.form.querySelector(`[data-preview=${angle}]`);
      const photo = state.photos.find(item => item.angle === angle);
      slot.replaceChildren();
      if (photo) {
        preview(state, photo).then(url => {
          if (!slot.isConnected || !state.deps.isCurrent()) return;
          const image = document.createElement('img');
          image.alt = { front: '正面实拍', side: '侧面实拍', top: '顶部实拍' }[angle];
          image.src = url;
          slot.replaceChildren(image);
        }).catch(error => status(state, error.message));
      }
    }
    state.form.querySelector('.photo-count').textContent = `已保存 ${state.photos.length} 张图片 · 至少正面、侧面、顶部各一张`;
  }

export async function upload(state, file, angle) {
    if (file.size > 5 * 1024 * 1024) throw new Error('单张图片不能超过5MB，请重新选择');
    const generation = (state.generations[angle] || 0) + 1;
    state.generations[angle] = generation;
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('图片读取失败，请重新选择'));
      reader.readAsDataURL(file);
    });
    if (!state.deps.isCurrent()) return;
    const photo = await state.deps.request('/upload', { content, angle });
    if (!state.deps.isCurrent() || (angle!=='extra' && state.generations[angle] !== generation)) return;
    if (angle !== 'extra') state.photos = state.photos.filter(item => item.angle !== angle);
    state.photos.push(photo);
    state.failed.delete(angle);
    drawPhotos(state);
    cache(state);
  }

export async function suspend() {
    const state = appState.draftEditor;
    if (!state) return;
    clearTimeout(state.timer);
    cache(state);
    if (state.form && state.deps.isCurrent() && !state.conflict) {
      await save(state).catch(() => {});
    }
    if (appState.draftEditor === state) appState.draftEditor = null;
    for (const url of state.urls) URL.revokeObjectURL(url);
  }

export function clearLocal(userId,productId,expectedId){
 const key=cacheKey(userId,productId);
 try{const local=JSON.parse(localStorage.getItem(key)||'null');if(!expectedId||local?.id===expectedId)localStorage.removeItem(key);}catch{}
 const active=appState.draftEditor;
 if(active?.deps.user.id===userId && (!expectedId||active.id===expectedId)){
  clearTimeout(active.timer);appState.draftEditor=null;
 }
}
