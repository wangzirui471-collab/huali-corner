'use strict';
// 基础设施层 · 发布草稿（F-02）
//
// 交接约定（第一阶段）：localStorage、按账号隔离、500ms 防抖、
// 恢复/丢弃提示、发布成功后清除。**这不是跨设备草稿**——跨设备草稿
// 需要服务端 drafts 表，属后续阶段；这里解决的是「刷新或离开页面后
// 刚写的内容全丢」。
//
// 图片不在此列：File 对象无法进 localStorage，草稿恢复后照片需要
// 重新选择（恢复提示里会说明）。

const PREFIX = 'zj.publish.draft.';
const DEBOUNCE_MS = 500;

function key(uid){ return PREFIX + String(uid); }

function safeStorage(){
  try{ return window.localStorage; }catch{ return null; }   // 隐私模式下直接放弃
}

export function loadDraft(uid){
  const store = safeStorage();
  if (!store) return null;
  try{
    const raw = store.getItem(key(uid));
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data && typeof data === 'object' && data.values && data.savedAt ? data : null;
  }catch{ return null; }
}

export function saveDraft(uid, values){
  const store = safeStorage();
  if (!store) return;
  try{
    store.setItem(key(uid), JSON.stringify({ values, savedAt: Date.now() }));
  }catch{ /* 超出配额就丢，草稿不能把页面搞坏 */ }
}

export function clearDraft(uid){
  const store = safeStorage();
  if (!store) return;
  try{ store.removeItem(key(uid)); }catch{}
}

// 500ms 防抖保存：input 事件很密，不值得每次敲键都写盘。
export function makeDraftSaver(uid){
  let timer = null;
  return values => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; saveDraft(uid, values); }, DEBOUNCE_MS);
  };
}
