'use strict';
// 基础设施层 · 与后端通信
// 公开演示版没有后端，全部走 public-demo.js 注入的本地快照。

import { state } from './state.js';

export async function api(path, data){
  if (window.HUALI_STATIC_DEMO) return window.hualiDemoApi(path, data);
  // 记下发起时的账号与渲染代次；如果请求返回前已经切换，就丢弃这次结果，
  // 免得旧请求把上一个账号的内容盖到新页面上。
  const session = state.token, epoch = state.renderId;
  const res = await fetch('/api'+path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {'Content-Type':'application/json', ...(state.token ? {Authorization:'Bearer '+state.token} : {})},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const body = await res.json();
  if (session !== state.token || epoch !== state.renderId) throw new Error('页面或账号已切换，请重试');
  if (!res.ok) {
    // 带上 HTTP 状态：调用方需要区分「409 资料被别人改了」和普通失败，
    // 靠比对中文错误文案太脆。message 保持原样，老调用方不受影响。
    const error = new Error(body.error || '请求失败');
    error.status = res.status;
    throw error;
  }
  return body;
}
