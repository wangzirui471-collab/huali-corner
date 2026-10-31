'use strict';
// 组件层 · 频道插画
// 内联 SVG，避免为每个频道再发一次图片请求。
// 配色跟随首页薄荷青主题：绿色系为主，暖色只留一小块做对比。

const shapes = {
  books:'<rect x="16" y="24" width="45" height="42" rx="6" fill="#2f8f7a"/><path d="M23 31h30v28H23z" fill="#c9e8dd"/><rect x="29" y="14" width="40" height="44" rx="5" fill="#0f7b63"/><path d="M36 22h23M36 29h17" stroke="#e5f5ef" stroke-width="4"/><rect x="17" y="62" width="51" height="6" rx="3" fill="#7fbfae"/>',
  living:'<path d="M24 20h35v26H24z" fill="#9fd0bf"/><rect x="13" y="38" width="54" height="21" rx="6" fill="#2f8f7a"/><rect x="18" y="57" width="7" height="14" rx="2" fill="#146355"/><rect x="56" y="57" width="7" height="14" rx="2" fill="#146355"/><path d="M28 23h22" stroke="#e5f5ef" stroke-width="4"/>',
  sports:'<ellipse cx="44" cy="29" rx="16" ry="23" transform="rotate(32 44 29)" fill="#e7f4ef" stroke="#2f8f7a" stroke-width="5"/><path d="M31 48l-15 22" stroke="#ff8f5e" stroke-width="8" stroke-linecap="round"/><path d="M35 15l15 31M30 26l24 1M32 36l20-2" stroke="#9fd0bf" stroke-width="2"/>',
  electronics:'<rect x="14" y="19" width="52" height="35" rx="5" fill="#3f7f76"/><rect x="19" y="24" width="42" height="25" rx="3" fill="#dff0ea"/><path d="M9 56h62l-7 10H16z" fill="#7fbfae"/><rect x="26" y="30" width="11" height="3.4" rx="1.7" fill="#ff8f5e"/><rect x="26" y="37" width="27" height="3.4" rx="1.7" fill="#bfe0d5"/><rect x="26" y="44" width="18" height="3.4" rx="1.7" fill="#bfe0d5"/>',
  all:'<path d="M19 28h45l6 39H13z" fill="#2f8f7a"/><path d="M29 30V21a12 12 0 0 1 24 0v9" fill="none" stroke="#146355" stroke-width="6"/><path d="M28 45l11 10 17-20" fill="none" stroke="#e5f5ef" stroke-width="5" stroke-linecap="round"/>'
};

export function categoryArt(kind){
  return `<svg viewBox="0 0 80 80" class="category-art" aria-hidden="true"><ellipse cx="41" cy="71" rx="28" ry="4" fill="#0f7b63" opacity=".12"/>${shapes[kind]||shapes.all}</svg>`;
}
