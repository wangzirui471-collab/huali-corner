/** 按需加载 Vue + Element Plus 办公面板，复用站点 API 的会话与错误处理。 */
import { state } from '../core/state.js';
import { api } from '../core/http.js';
import { isOwner } from '../core/roles.js';
import { subscribeSession } from '../core/session.js';

/** 在当前所有者身份下打开工单工具；退出登录后面板自动销毁。 */
export async function openOfficeTickets(initial){
  if (!isOwner(state.me)) throw new Error('仅平台所有者可使用工单办公');
  const token = state.token;
  if (!document.querySelector('#hc-office-styles')){
    const link = document.createElement('link');
    link.id = 'hc-office-styles'; link.rel = 'stylesheet';
    link.href = '/assets/office/office-panel.css';
    document.head.appendChild(link);
  }
  const panel = await import('/assets/office/office-panel.js');
  if (token !== state.token || !isOwner(state.me)) return;
  panel.openOfficeTickets({ api, initial, onAccountChange: subscribeSession,
    authorized: () => token === state.token && isOwner(state.me) });
}
