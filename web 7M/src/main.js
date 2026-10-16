'use strict';
// 入口 · 拉配置、恢复会话、装好监听器、渲染首屏
// 模块加载顺序本身就是初始化顺序：router.js 被 import 时会把 render 注册进 core/nav.js。

import { $ } from './core/dom.js';
import { state, loadCart } from './core/state.js';
import { api } from './core/http.js';
import { render } from './router.js';
import { closeModal } from './core/shell.js';
import { registerActions } from './actions/index.js';
import { registerChangeHandlers } from './actions/change.js';

registerActions();
registerChangeHandlers();

window.addEventListener('hashchange', render);
window.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeModal(); });
// 顶栏是 sticky 的，高度随断点变化，CSS 的 --header-h 只能在运行时量出来。
window.addEventListener('resize', () => {
  const m = document.querySelector('.market-header');
  if (m) document.documentElement.style.setProperty('--header-h', m.offsetHeight+'px');
});

(async () => {
  try{
    state.config = await api('/config');
    if (state.token){
      try{
        state.me = await api('/me');
        loadCart();
      }catch{
        // token 过期或被服务端作废：清掉本地会话，以游客身份继续逛。
        state.token = '';
        sessionStorage.removeItem('hc-token');
      }
    }
    await render();
  }catch(err){
    $('#app').textContent = '服务暂不可用：'+err.message;
  }
})();
