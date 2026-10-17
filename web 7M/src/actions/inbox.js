import { state as appState } from '../core/state.js';
import { panel,refresh,rows,permissionText,preferenceKey } from '../core/inbox.js';
export async function inboxClick(button){
    if (!button || !appState.inbox?.context.isCurrent()) return;
    const state = appState.inbox, context = state.context;
    button.disabled = true;
    try {
      const action = button.dataset.inboxAction;
      if (action === 'open') {
        await context.request('/notifications/read', {id:Number(button.dataset.notificationId)});
        if (!context.isCurrent()) return;
        context.go(({order:'orders',ticket:'ticket',chat:'messages',product:'product'}[button.dataset.kind]||'messages') + '/' + button.dataset.entity);
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
        if (!context.isCurrent() || appState.inbox !== state) return;
        try { localStorage.setItem(preferenceKey(owner), permission === 'granted' ? 'enabled' : 'disabled'); } catch { context.toast('本机无法保存设置，站内通知仍可用'); return; }
        context.toast(permission === 'granted' ? '已开启本机浏览器提醒，需保持网页运行；部分手机可能不支持' : permissionText());
      } else if (action === 'disable') {
        localStorage.removeItem(preferenceKey(context.user.id));
        for (const notice of state.windows) notice.close();
        context.toast('已关闭本机浏览器提醒，站内通知保留');
      }
    } catch (error) { if (context.isCurrent()) context.toast(error.message); }
    finally { button.disabled = false; }
  }
