/** 将开源 Vue/Element Plus 工单面板挂到现有应用，不替换路由或业务状态。 */
import { createApp } from 'vue';
import OfficeTickets from './OfficeTickets.vue';
// 使用组件库官方样式，包含遮罩、焦点与浮层依赖；仅打开办公面板时加载。
import 'element-plus/dist/index.css';

let current = null;

/** 打开单一面板，会话或角色变化时卸载并清除工单内容。 */
export function openOfficeTickets(options){
  current?.();
  const root = document.createElement('div');
  document.body.appendChild(root);
  let app;
  let timer;
  let unsubscribe;
  /** 关闭并释放监听器，避免跨账号保留客户资料。 */
  const dispose = () => {
    clearInterval(timer);
    unsubscribe?.();
    window.removeEventListener('hashchange', dispose);
    app?.unmount();
    root.remove();
    current = null;
  };
  app = createApp(OfficeTickets, { ...options, close: dispose });
  app.mount(root);
  unsubscribe = options.onAccountChange?.(dispose);
  timer = setInterval(() => { if (!options.authorized()) dispose(); }, 300);
  window.addEventListener('hashchange', dispose);
  current = dispose;
}
