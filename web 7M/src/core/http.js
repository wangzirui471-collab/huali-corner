'use strict';
// Shared JSON transport. Never expose proxy HTML or invalidate a session on a server error.
import { state } from './state.js';

// 列表与页面入口数据的短 TTL 缓存（性能优化，2026-10-21 / 2026-10-29）：
// - 线上一次接口往返 0.7–3 秒，切页慢几乎全部来自「等网络」，不是渲染；
// - 缓存按 token 隔离，避免换账号看到别人的数据；命中返回浅拷贝，防止调用方排序/过滤污染；
// - 任何写操作（POST）立即清空；分页请求（offset / page>1）不缓存；
// - 轮询接口（/messages、/rooms）不在此列，聊天和通知不能被缓存住。
// 新增页面入口接口时必须在 CACHE_RULES 登记，否则切页会多等一个完整往返。
const CACHE_RULES = [
  // TTL 只决定「多久后需要重新取」，任何 POST 都会立刻清空，不必为了新鲜度把 TTL 压得很短。
  [/^\/(products|posts)(\?|$)/, 60000],
  [/^\/(product|profile|user\/profile)(\?|$)/, 120000],
  [/^\/(my-products|orders|offers|me)(\?|$)/, 60000],
  [/^\/(order|want|friend\/state|notifications)(\?|$)/, 30000],
  [/^\/(comments|ticket|user\/dossier|credit\/history)(\?|$)/, 30000],
  [/^\/(admin|tickets|reconcile|support\/sessions|product\/removed)(\?|$)/, 15000],
];
const listCache = new Map();
// 并发去重：同一份数据在飞的时候，第二个调用者等同一个 Promise，
// 不再发第二次请求（切页时「预取 + 页面」同时要同一份数据是常态）。
const inflight = new Map();

function ttlFor(path){
  for (const [re, ttl] of CACHE_RULES) if (re.test(path)) return ttl;
  return 0;
}
function cacheable(path){
  if (!ttlFor(path)) return false;
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
function writeList(path, data, key = cacheKey(path)){
  if (listCache.size >= 120) listCache.clear();  // 搜索词/工作台多时不无限增长
  listCache.set(key, { data: Array.isArray(data) ? data.slice() : data, at: Date.now() });
}
function clearList(){ listCache.clear(); }
function clone(data){ return Array.isArray(data) ? data.slice() : data; }

// 页面/账号切换守卫：请求发出后如果已经换了页面或账号，结果必须丢弃。
function guard(session, epoch, opts){
  if (session !== state.token || (!opts.global && epoch !== state.renderId)){
    throw new Error('页面或账号已切换，请重试');
  }
}

// 空闲预取：只填充缓存，不触发渲染，失败静默。
// 用于首页 / 社区互相预热，以及切页前按导航意图预热目标页数据。
export function prefetch(path){
  if (window.HUALI_STATIC_DEMO || !cacheable(path) || readList(path) !== null) return;
  api(path).catch(() => {});
}

export async function api(path, data, opts = {}){
  if (window.HUALI_STATIC_DEMO) return window.hualiDemoApi(path, data);
  const write = data !== undefined;
  const session = state.token, epoch = state.renderId;

  if (!write && cacheable(path)){
    const cached = readList(path);
    if (cached !== null){
      // 命中缓存仍要遵守「页面/账号已切换」守卫，避免旧页面盖掉新页面。
      guard(session, epoch, opts);
      return clone(cached);
    }
    const key = cacheKey(path);
    let running = inflight.get(key);
    if (!running){
      // key 在发请求时固定：换账号瞬间返回的旧响应不能写进新账号的缓存。
      running = fetchJson(path, data, opts).then(body => {
        writeList(path, body, key);
        return body;
      }).finally(() => {
        if (inflight.get(key) === running) inflight.delete(key);
      });
      inflight.set(key, running);
    }
    const body = await running;
    guard(session, epoch, opts);
    return clone(body);
  }

  const body = await fetchJson(path, data, opts);
  guard(session, epoch, opts);
  if (write) clearList();
  return body;
}

/** 请求截止时间覆盖响应头和JSON正文；超时保留会话，不自动重发结果未知的写操作。 */
async function fetchJson(path, data, opts){
  const duration = opts.timeout === undefined ? 30000 : opts.timeout;
  const ctrl = duration ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), duration) : null;
  try{
    const res = await fetch('/api'+path, {
      method: data === undefined ? 'GET' : 'POST',
      headers: {'Content-Type':'application/json', ...(state.token ? {Authorization:'Bearer '+state.token} : {})},
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: ctrl ? ctrl.signal : undefined
    });
    const type = (res.headers.get('Content-Type') || '').toLowerCase();
    let body;
    if (type.includes('application/json') || type.includes('+json')){
      try { body = await res.json(); }
      catch(err){
        if (ctrl && ctrl.signal.aborted) throw err;
        // JSON损坏仍由协议错误分支统一处理，不能把代理页面当成身份失效。
      }
    }
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
    return body;
  }catch(err){
    if (ctrl && ctrl.signal.aborted){
      const timeout = new Error(data === undefined
        ? '请求超时，请稍后重试；当前登录状态已保留'
        : '请求超时，操作结果尚未确认；请先查看状态，避免重复提交');
      timeout.status = 504;
      timeout.code = 'REQUEST_TIMEOUT';
      throw timeout;
    }
    throw err;
  }finally{
    if (timer) clearTimeout(timer);
  }
}
