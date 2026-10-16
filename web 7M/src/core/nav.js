'use strict';
// 基础设施层 · 路由跳转
// 页面需要「重新渲染当前页」时会回调 render，但 render 定义在 router.js
// 而 router.js 又要 import 所有页面 —— 直接用会成环。
// 这里用一个注册钩子把依赖方向反过来：router 注册，其他模块只管调用。

let renderer = () => {};

export function setRenderer(fn){ renderer = fn; }

export function render(){ return renderer(); }

export function go(path){
  if (location.hash === '#'+path) render();
  else location.hash = path;
}
