'use strict';
// 基础设施层 · 路由跳转
// 页面需要「重新渲染当前页」时会回调 render，但 render 定义在 router.js
// 而 router.js 又要 import 所有页面 —— 直接用会成环。
// 这里用一个注册钩子把依赖方向反过来：router 注册，其他模块只管调用。

import { startProgress } from './progress.js';
import {routePath} from './route-path.js';

let renderer = () => {};
let router;

/** 框架入口注入唯一 Vue Router，不让业务模块反向依赖 Vue 入口。 */
export function configureNavigation(instance){ router = instance; }

export function setRenderer(fn){ renderer = fn; }

export function render(){ return renderer(); }

/** 交给 Vue Router 跳转；重复点击当前页保留原来的重新渲染行为。 */
export function go(path){
  // 点击即出进度条：路由要等接口回来才画页面，慢网络下这是唯一反馈。
  startProgress();
  const target = '/' + routePath(path);
  if (router){
    if (router.currentRoute.value.fullPath === target) return render();
    return router.push(target);
  }
  if (routePath() === routePath(path)) return render();
  location.hash = path;
}
