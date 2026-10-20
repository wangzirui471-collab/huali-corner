'use strict';
// Shared JSON transport. Never expose proxy HTML or invalidate a session on a server error.
import { state } from './state.js';

export async function api(path, data){
  if (window.HUALI_STATIC_DEMO) return window.hualiDemoApi(path, data);
  const session = state.token, epoch = state.renderId;
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
  return body;
}
