import { state as appState } from './state.js';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const preferenceKey = id => 'zj-browser-notices-' + id;
export function preference(id) { try { return localStorage.getItem(preferenceKey(id)) === 'enabled'; } catch { return false; } }

export function permissionText() {
    if (!window.isSecureContext || !('Notification' in window)) return '此环境不支持系统提醒，站内通知正常使用；部分手机需安装到主屏幕。';
    if (Notification.permission === 'denied') return '系统提醒被拒绝；可在浏览器网站设置中更改，站内通知正常使用。';
    return '仅网页保持运行时尝试系统提醒；关窗、手机后台限制或断网时不保证送达。微信订阅消息尚未接入。';
  }

export function badges(count) {
    document.querySelectorAll('[data-go="messages"]').forEach(button => {
      button.querySelector('[data-notification-count]')?.remove();
      if (count) {
        const badge = document.createElement('span');
        badge.dataset.notificationCount = '';
        badge.className = 'notification-badge';
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.setAttribute('aria-label', `订单售后未读${count}条`);
        button.append(badge);
      }
    });
  }

export function stop() {
    if (appState.inbox) { clearInterval(appState.inbox.timer); for (const notice of appState.inbox.windows) notice.close(); }
    appState.inbox = null;
    badges(0);
  }

export async function refresh() {
    const state = appState.inbox;
    if (!state || state.busy || !state.context.isCurrent()) return;
    state.busy = true;
    try {
      const result = await state.context.request('/notifications');
      if (appState.inbox !== state || !state.context.isCurrent()) return;
      state.count=result.unread_count;
      badges(state.count);
      const refreshButton = document.querySelector('[data-inbox-action="refresh"]');
      if (refreshButton && result.latest_id > Number(refreshButton.dataset.latest || 0)) {
        refreshButton.classList.add('has-new');
        refreshButton.title = '有新通知，点击刷新列表';
      }
      if (state.initialized && preference(state.context.user.id) && 'Notification' in window && Notification.permission === 'granted') {
        // One generic desktop alert per polling batch; no address, phone or dispute content.
        const fresh = result.items.filter(item => !item.read_at && item.id > state.latest);
        if (fresh.length) {
          try {
            const notice = new Notification('转角有新的订单／售后通知', {
              body: '请进入消息中心查看处理。交易资金为模拟记录。', tag: 'zj-inbox-' + state.context.user.id,
            });
            state.windows.add(notice);
            notice.onclose = () => state.windows.delete(notice);
            notice.onclick = () => {
              notice.close();
              if (appState.inbox === state && state.context.isCurrent()) { window.focus(); state.context.go('messages'); }
            };
          } catch { /* Some mobile browsers expose Notification but require a push service. */ }
        }
      }
      state.latest = Math.max(state.latest, result.latest_id);
      state.initialized = true;
    } catch {
      if (appState.inbox === state) document.querySelector('[data-inbox-connection]')?.replaceChildren(document.createTextNode('通知暂未同步，可手动刷新；不影响已有订单。'));
    } finally { state.busy = false; }
  }

export function attach(context) {
    if (!context) { stop(); return; }
    if (!appState.inbox || appState.inbox.context.user.id !== context.user.id || appState.inbox.context.session !== context.session) {
      stop();
      appState.inbox = {context, latest:0, count:0, initialized:false, busy:false, windows:new Set(), timer:setInterval(refresh, 5000)};
      refresh();
    } else {
      appState.inbox.context = context;
      refresh();
    }
  }

export function rows(items, context) {
    return items.map(item => `<button class="notification-row ${item.read_at ? '' : 'unread'}" data-inbox-action="open" data-notification-id="${item.id}" data-kind="${escape(item.entity_type)}" data-entity="${item.entity_id}"><span class="notification-symbol">${item.entity_type === 'order' ? '单' : '助'}</span><span><b>${escape(item.title)}</b><small>${item.entity_type === 'order' ? '订单' : '工单'} #${item.entity_id} · ${escape(context.date(item.created_at))}${item.read_at ? ' · 已读' : ' · 未读'}</small></span><span aria-hidden="true">›</span></button>`).join('');
  }

export async function panel(context) {
    const result = await context.request('/notifications');
    return `<section class="panel inbox-panel" data-notification-center><div class="section-heading"><h2>订单与售后通知</h2><button class="text-button" data-inbox-action="refresh" data-latest="${result.latest_id}">刷新通知</button></div><p class="muted">仅显示你的订单和有权限处理的工单。未读 ${result.unread_count} 条。</p><div class="stack"><button class="btn secondary" data-inbox-action="read-all" data-through="${result.latest_id}" ${!result.unread_count ? 'disabled' : ''}>全部标为已读</button><button class="btn secondary" data-inbox-action="permission">开启浏览器提醒</button><button class="text-button" data-inbox-action="disable">关闭本机浏览器提醒</button></div><p class="muted" data-inbox-connection>${escape(permissionText())}</p><div class="notification-list">${rows(result.items,context) || '<p class="muted">暂无订单或售后通知。</p>'}</div>${result.has_more ? `<button class="btn secondary" data-inbox-action="more" data-before="${result.items.at(-1).id}">加载更早通知</button>` : ''}</section>`;
  }
export const redraw=()=>badges(appState.inbox?.context.isCurrent()?appState.inbox.count:0);
