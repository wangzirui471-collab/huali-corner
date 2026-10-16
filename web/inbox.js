/* Persistent order/support inbox. Browser notifications are opt-in, page-alive only. */
(() => {
  'use strict';
  let active = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const preferenceKey = id => 'zj-browser-notices-' + id;
  function preference(id) { try { return localStorage.getItem(preferenceKey(id)) === 'enabled'; } catch { return false; } }
  function permissionText() {
    if (!window.isSecureContext || !('Notification' in window)) return '此环境不支持系统提醒，站内通知正常使用；部分手机需安装到主屏幕。';
    if (Notification.permission === 'denied') return '系统提醒被拒绝；可在浏览器网站设置中更改，站内通知正常使用。';
    return '仅网页保持运行时尝试系统提醒；关窗、手机后台限制或断网时不保证送达。微信订阅消息尚未接入。';
  }
  function badges(count) {
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
  function stop() {
    if (active) { clearInterval(active.timer); for (const notice of active.windows) notice.close(); }
    active = null;
    badges(0);
  }
  async function refresh() {
    const state = active;
    if (!state || state.busy || !state.context.isCurrent()) return;
    state.busy = true;
    try {
      const result = await state.context.request('/notifications');
      if (active !== state || !state.context.isCurrent()) return;
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
              if (active === state && state.context.isCurrent()) { window.focus(); state.context.go('messages'); }
            };
          } catch { /* Some mobile browsers expose Notification but require a push service. */ }
        }
      }
      state.latest = Math.max(state.latest, result.latest_id);
      state.initialized = true;
    } catch {
      if (active === state) document.querySelector('[data-inbox-connection]')?.replaceChildren(document.createTextNode('通知暂未同步，可手动刷新；不影响已有订单。'));
    } finally { state.busy = false; }
  }
  function attach(context) {
    if (!context) { stop(); return; }
    if (!active || active.context.user.id !== context.user.id || active.context.session !== context.session) {
      stop();
      active = {context, latest:0, count:0, initialized:false, busy:false, windows:new Set(), timer:setInterval(refresh, 5000)};
      refresh();
    } else {
      active.context = context;
      refresh();
    }
  }
  function rows(items, context) {
    return items.map(item => `<button class="notification-row ${item.read_at ? '' : 'unread'}" data-inbox-action="open" data-notification-id="${item.id}" data-kind="${escape(item.entity_type)}" data-entity="${item.entity_id}"><span class="notification-symbol">${item.entity_type === 'order' ? '单' : '助'}</span><span><b>${escape(item.title)}</b><small>${item.entity_type === 'order' ? '订单' : '工单'} #${item.entity_id} · ${escape(context.date(item.created_at))}${item.read_at ? ' · 已读' : ' · 未读'}</small></span><span aria-hidden="true">›</span></button>`).join('');
  }
  async function panel(context) {
    const result = await context.request('/notifications');
    return `<section class="panel inbox-panel" data-notification-center><div class="section-heading"><h2>订单与售后通知</h2><button class="text-button" data-inbox-action="refresh" data-latest="${result.latest_id}">刷新通知</button></div><p class="muted">仅显示你的订单和有权限处理的工单。未读 ${result.unread_count} 条。</p><div class="stack"><button class="btn secondary" data-inbox-action="read-all" data-through="${result.latest_id}" ${!result.unread_count ? 'disabled' : ''}>全部标为已读</button><button class="btn secondary" data-inbox-action="permission">开启浏览器提醒</button><button class="text-button" data-inbox-action="disable">关闭本机浏览器提醒</button></div><p class="muted" data-inbox-connection>${escape(permissionText())}</p><div class="notification-list">${rows(result.items,context) || '<p class="muted">暂无订单或售后通知。</p>'}</div>${result.has_more ? `<button class="btn secondary" data-inbox-action="more" data-before="${result.items.at(-1).id}">加载更早通知</button>` : ''}</section>`;
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-inbox-action]');
    if (!button || !active?.context.isCurrent()) return;
    const state = active, context = state.context;
    button.disabled = true;
    try {
      const action = button.dataset.inboxAction;
      if (action === 'open') {
        await context.request('/notifications/read', {id:Number(button.dataset.notificationId)});
        if (!context.isCurrent()) return;
        context.go(button.dataset.kind === 'order' ? 'orders/' + button.dataset.entity : 'ticket/' + button.dataset.entity);
        await refresh();
      } else if (action === 'read-all') {
        await context.request('/notifications/read', {through_id:Number(button.dataset.through)});
        if (!context.isCurrent()) return;
        const html = await panel(context);
        document.querySelector('[data-notification-center]').outerHTML = html;
        await refresh();
      } else if (action === 'refresh') {
        const html = await panel(context);
        if (!context.isCurrent()) return;
        const current = document.querySelector('[data-notification-center]');
        if (current) current.outerHTML = html;
        await refresh();
      } else if (action === 'more') {
        const result = await context.request('/notifications?before=' + Number(button.dataset.before));
        if (!context.isCurrent() || !button.isConnected) return;
        button.closest('[data-notification-center]').querySelector('.notification-list').insertAdjacentHTML('beforeend', rows(result.items,context));
        if (result.has_more) button.dataset.before = result.items.at(-1).id;
        else button.remove();
      } else if (action === 'permission') {
        if (!window.isSecureContext || !('Notification' in window)) { context.toast(permissionText()); return; }
        const owner = context.user.id;
        const permission = await Notification.requestPermission();
        if (!context.isCurrent() || active !== state) return;
        try { localStorage.setItem(preferenceKey(owner), permission === 'granted' ? 'enabled' : 'disabled'); } catch { context.toast('本机无法保存设置，站内通知仍可用'); return; }
        context.toast(permission === 'granted' ? '已开启本机浏览器提醒，需保持网页运行；部分手机可能不支持' : permissionText());
      } else if (action === 'disable') {
        localStorage.removeItem(preferenceKey(context.user.id));
        for (const notice of state.windows) notice.close();
        context.toast('已关闭本机浏览器提醒，站内通知保留');
      }
    } catch (error) { if (context.isCurrent()) context.toast(error.message); }
    finally { button.disabled = false; }
  });
  window.ZJInbox = {attach, stop, refresh, panel, redraw:()=>badges(active?.context.isCurrent()?active.count:0)};
})();
