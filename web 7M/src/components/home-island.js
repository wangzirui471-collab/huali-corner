'use strict';
// 岛屿加载 · 逛逛页主视觉（Vue + Element Plus）
// 岛只画轮播；频道行、商品流、筛选和跳转全部留在原生层，
// 岛取不到（离线、构建缺失、CDN 抖动）就保留原生兜底轮播，首页不跟着白屏。
import { asset } from '../core/asset.js';

const ISLAND_JS = '/assets/home/home-island.js';
const ISLAND_CSS = '/assets/home/home-island.css';
// 首屏数据通常比岛先到；超过这个等待就不再让页面空转，直接用兜底。
const MOUNT_TIMEOUT = 1500;

let island;

// 动态 import 的相对路径是按「当前模块」解析的，演示版挂在子路径下会指到 /src/assets 去；
// 统一先按文档基址算成绝对 URL，站点根和子路径托管都拿到同一个文件。
function islandURL(path){
  return new URL(asset(path), document.baseURI).href;
}

function loadIsland(){
  if (!island){
    if (!document.querySelector('#hc-home-styles')){
      const link = document.createElement('link');
      link.id = 'hc-home-styles'; link.rel = 'stylesheet'; link.href = islandURL(ISLAND_CSS);
      document.head.appendChild(link);
    }
    island = import(islandURL(ISLAND_JS)).catch(error => { island = null; throw error; });
  }
  return island;
}

// 测试与降级开关：window.HC_HOME_ISLAND === false 时强制走原生兜底轮播。
export function homeIslandEnabled(){
  return !('HC_HOME_ISLAND' in window) || window.HC_HOME_ISLAND !== false;
}

// 与首屏请求并行取岛，真正挂载时基本零等待。
export function preloadHomeIsland(){
  if (homeIslandEnabled()) loadIsland().catch(() => {});
}

export async function mountHomeChrome(root, props){
  if (!root || !homeIslandEnabled()) return null;
  let module = null;
  try{
    module = await Promise.race([
      loadIsland(),
      new Promise(resolve => setTimeout(() => resolve(null), MOUNT_TIMEOUT))
    ]);
  }catch(error){ return null; }
  // 等岛期间用户可能已经切页，容器都不在了就别再挂。
  if (!module || !root.isConnected) return null;
  return module.mountHomeChrome(root, props);
}
