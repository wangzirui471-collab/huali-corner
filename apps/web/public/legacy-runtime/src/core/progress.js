'use strict';
// 基础设施层 · 路由切换的顶部细进度条
//
// 页面数据都要等接口回来才 shell()，这段时间屏幕上没有任何变化——网络慢时
// 用户会觉得「点了没反应」。进度条在点击/路由变化的那一刻就出现，页面画完
// 由 router 收起；15 秒兜底自动消失，避免异常时永久停在顶上。

let timer = null;
let bar = null;

function ensure(){
  if (bar && bar.isConnected) return bar;
  bar = document.createElement('div');
  bar.className = 'route-progress';
  bar.innerHTML = '<i></i>';
  document.body.appendChild(bar);
  return bar;
}

export function startProgress(){
  ensure().dataset.on = '1';
  clearTimeout(timer);
  timer = setTimeout(stopProgress, 15000);
}

export function stopProgress(){
  clearTimeout(timer);
  if (bar) bar.dataset.on = '0';
}
