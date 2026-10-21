'use strict';
// Shared JSON transport. Never expose proxy HTML or invalidate a session on a server error.
import { state } from './state.js';

// 列表首屏短 TTL 缓存（性能优化，2026-10-21）：
// - 缓存公开列表 + 工作台列表的首屏，按 token 隔离，避免换账号看到别人的数据；
// - 工作台数据变化快，用更短 TTL（10s）；公开列表 30s；
// - 任何写操作（POST）立即清空；分页请求（offset / page>1）不缓存；
// - 命中缓存也走「页面/账号已切换」守卫，命中后返回浅拷贝，防止调用方排序/过滤污染缓存。
// 注意：轮询接口（/messages、/notifications、/rooms）不在此列，避免聊天/通知被缓存住。
const LIST_TTL = 30000;
const WORK_TTL = 10000;
const listCache = new Map();
const CACHEABLE = /^\/(products|posts|admin|tickets|reconcile|support\/sessions|product\/removed|orders|my-products|credit\/history)(\?|$)/;
const WORKBENCH = /^\/(admin|tickets|reconcile|support\/sessions|product\/removed)(\?|$)/;

function ttlFor(path){ return WORKBENCH.test(path) ? WORK_TTL : LIST_TTL; }
function cacheable(path){
  if (!CACHEABLE.test(path)) return false;
  if (/[?&]offset=/.test(path)) return false;
  const m = path.match(/[?&]page=(\d+)/);
  return !(m && Number(m[1]) > 1);
}
function cacheKey(path){ return (state.token || 'anon') + '::' + path; }
function readList(path){
  const key = cacheKey(path), hit = listCache.get(key);
  if (!hit) return null;
  if (Date.now() - hit.at > ttlFor(path)){ listCache.delete(key); return null; }
  return hit.data;
}
function writeList(path, data){
  if (listCache.size >= 80) listCache.clear();  // 搜索词/工作台多时不无限增长
  listCache.set(cacheKey(path), { data: Array.isArray(data) ? data.slice() : data, at: Date.now() });
}
function clearList(){ listCache.clear(); }

// 空闲预取：只填充缓存，不触发渲染，失败静默。
// 用于首页 / 社区互相预热，切页时直接命中缓存。
export function prefetch(path){
  if (window.HUALI_STATIC_DEMO || !cacheable(path) || readList(path) !== null) return;
  api(path).catch(() => {});
}

export async function api(path, data){
  if (window.HUALI_STATIC_DEMO) return window.hualiDemoApi(path, data);
  const write = data !== undefined;
  const session = state.token, epoch = state.renderId;
  if (!write && cacheable(path)){
    const cached = readList(path);
    if (cached !== null){
      // 命中缓存仍要遵守「页面/账号已切换」守卫，避免旧页面盖掉新页面。
      if (session !== state.token || epoch !== state.renderId) throw new Error('页面或账号已切换，请重试');
      return Array.isArray(cached) ? cached.slice() : cached;
    }
  }
  const res = await fetch('/api'+path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {'Content-Type':'application/json', ...(session ? {Authorization:'Bearer '+session} : {})},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const type = (res.headers.get('Content-Type') || '').toLowerCase();
  let body;
  if (type.includes('application/json') || type.includes('+json')){
    try { body = await res.json(); } catch { /* malformed response is handled below */ }
  }
  if (session !== state.token || epoch !== state.renderId) throw new Error('页面或账号已切换，请重试');
  if (!body || typeof body !== 'object'){
    const error = new Error(res.status >= 500
      ? '服务暂时不可用，请稍后重试；当前登录状态已保留'
      : '接口响应异常，请刷新页面重试；若仍失败请联系管理员');
    error.status = res.status;
    error.code = 'INVALID_API_RESPONSE';
    throw error;
  }
  if (!res.ok){
    const error = new Error(body.error || '请求失败');
    error.status = res.status;
    throw error;
  }
  if (write) clearList();
  else if (cacheable(path)) writeList(path, body);
  return body;
}
