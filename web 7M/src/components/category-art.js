'use strict';
// 组件层 · 频道插画
// 内联 SVG，避免为每个频道再发一次图片请求。

const shapes = {
  books:'<rect x="16" y="24" width="45" height="42" rx="6" fill="#fc7048"/><path d="M23 31h30v28H23z" fill="#ffb18f"/><rect x="29" y="14" width="40" height="44" rx="5" fill="#ffcc45"/><path d="M36 22h23M36 29h17" stroke="#fff4bb" stroke-width="4"/><rect x="17" y="62" width="51" height="6" rx="3" fill="#eeb653"/>',
  living:'<path d="M24 20h35v26H24z" fill="#97b7a2"/><rect x="13" y="38" width="54" height="21" rx="6" fill="#5e9276"/><rect x="18" y="57" width="7" height="14" rx="2" fill="#476c58"/><rect x="56" y="57" width="7" height="14" rx="2" fill="#476c58"/><path d="M28 23h22" stroke="#b9d4bd" stroke-width="4"/>',
  sports:'<ellipse cx="44" cy="29" rx="16" ry="23" transform="rotate(32 44 29)" fill="#edf4ff" stroke="#797fb0" stroke-width="5"/><path d="M31 48l-15 22" stroke="#efaa64" stroke-width="8" stroke-linecap="round"/><path d="M35 15l15 31M30 26l24 1M32 36l20-2" stroke="#afb6d6" stroke-width="2"/>',
  electronics:'<rect x="14" y="19" width="52" height="35" rx="5" fill="#7c93ae"/><rect x="19" y="24" width="42" height="25" rx="3" fill="#e3edf9"/><path d="M9 56h62l-7 10H16z" fill="#a2b5cb"/><rect x="26" y="30" width="11" height="3.4" rx="1.7" fill="#ffcc38"/><rect x="26" y="37" width="27" height="3.4" rx="1.7" fill="#bcd0e4"/><rect x="26" y="44" width="18" height="3.4" rx="1.7" fill="#bcd0e4"/>',
  // 免费送是「价格 0」的过滤，不是分类：用礼盒 + 蝴蝶结，和四个分类的物件插画区分开。
  free:'<rect x="14" y="34" width="52" height="34" rx="6" fill="#ffcc38"/><path d="M14 45h52M40 34v34" stroke="#fff6d8" stroke-width="5"/><path d="M31 34c-9 0-13-10-6-13s9 7 6 13zm18 0c9 0 13-10 6-13s-9 7-6 13z" fill="#f49a24"/>',
  all:'<path d="M19 28h45l6 39H13z" fill="#ffbf24"/><path d="M29 30V21a12 12 0 0 1 24 0v9" fill="none" stroke="#f49a24" stroke-width="6"/><path d="M28 45l11 10 17-20" fill="none" stroke="#fff4c9" stroke-width="5" stroke-linecap="round"/>'
};

export function categoryArt(kind){
  return `<svg viewBox="0 0 80 80" class="category-art" aria-hidden="true"><ellipse cx="41" cy="71" rx="28" ry="4" fill="#000" opacity=".06"/>${shapes[kind]||shapes.all}</svg>`;
}
