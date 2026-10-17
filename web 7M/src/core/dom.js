'use strict';
// 基础设施层 · DOM 与图标
// 只依赖浏览器 API，不 import 任何本项目模块，避免循环依赖。

export const $ = s => document.querySelector(s);

export const e = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export const icons = {
  home:'M3 10 12 3l9 7v11h-6v-7H9v7H3z',
  community:'M4 4h16v12H8l-4 4z',
  plus:'M12 4v16M4 12h16',
  message:'M4 4h16v13H8l-4 4zM8 9h8M8 13h5',
  user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 22v-2a8 8 0 0 1 16 0v2',
  search:'M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  heart:'M12 21 3 12C-3 3 7-1 12 6c5-7 15-3 9 6z',
  arrow:'M4 12h16M14 6l6 6-6 6',
  book:'M3 3h8l1 2 1-2h8v17h-8l-1 1-1-1H3zM12 5v16',
  chair:'M6 3h12v10H6zM3 13h18v4H3zM5 17v5M19 17v5',
  ball:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M8 4l2 7-5 5M16 4l-2 7 5 5M10 11h4l2 6-4 4-4-4z',
  bag:'M4 7h16l1 15H3zM8 8V5a4 4 0 0 1 8 0v3',
  check:'M4 12l5 5L20 6',
  clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M12 6v6l4 2',
  shield:'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6zM8 12l3 3 5-6',
  close:'M5 5l14 14M19 5 5 19',
  pin:'M19 9c0 6-7 13-7 13S5 15 5 9a7 7 0 0 1 14 0M14 9a2 2 0 1 1-4 0 2 2 0 0 1 4 0',
  share:'M8 12 17 5M8 12l9 7M6 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6M19 2a3 3 0 1 1 0 6 3 3 0 0 1 0-6M19 16a3 3 0 1 1 0 6 3 3 0 0 1 0-6',
  device:'M9 2h6a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2M11 18h2',
  edit:'M4 20h4L20 8l-4-4L4 16zM14 6l4 4',
  trash:'M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13h10l1-13M10 11v6M14 11v6',
  refresh:'M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4',
  camera:'M3 8h4l2-3h6l2 3h4v12H3zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
  filter:'M4 6h16M7 12h10M10 18h4',
  down:'M6 9l6 6 6-6',
  tag:'M3 12V4h8l9 9-8 8zM7.5 7.5h.01',
  truck:'M3 7h11v9H3zM14 10h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
  bell:'M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 0 0 4 0'
};

export const icon = (name, cls='') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[name]||icons.bag}"/></svg>`;

export function toast(text){
  $('#toast').textContent = text;
  $('#toast').classList.add('show');
  setTimeout(() => $('#toast').classList.remove('show'), 3500);
}

// 幂等请求标识。crypto.randomUUID 只在安全上下文（https / localhost / 127.0.0.1）里存在，
// 而试用版经常被同学用局域网 IP 以 http 打开 —— 那里 randomUUID 是 undefined，
// 结算和发消息会直接抛 TypeError。getRandomValues 不受安全上下文限制，用它兜底。
export function uid(){
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, x => x.toString(16).padStart(2,'0')).join('');
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
