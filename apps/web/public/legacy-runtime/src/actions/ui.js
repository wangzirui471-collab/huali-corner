'use strict';
// 事件层 · 纯界面交互（不涉及业务数据）

import { $, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { modal, closeModal } from '../core/shell.js';
import { selectField } from '../components/forms.js';

export const clicks = {
  close: () => closeModal(),

  // 错误页的「重新加载」：整页重来一次，比让用户自己找刷新按钮直接。
  'reload-page': () => location.reload(),

  // 演示商品的配图是背景裁切的拼图，没有别的角度可换；只有真实上传的照片才切 src。
  photo: b => {
    if (!document.querySelector('.detail-photo .photo-sprite')) $('#main-photo').src = b.dataset.url;
  },

  async share(){
    await navigator.clipboard.writeText(location.href);
    toast('商品链接已复制，分享不包含私密信息');
  },

  'open-filter'(){
    modal(`<h2>筛选</h2><form id="filter-form">${selectField('分类','category',[['','全部'],['books','二手书'],['living','宿舍生活'],['sports','运动闲置'],['electronics','电子产品']])}${selectField('排序','sort',[['','综合推荐'],['price','价格从低到高']])}<button class="btn primary full">应用筛选</button></form>`);
    const c = document.querySelector('#filter-form [name=category]');
    if (c) c.value = state.filter.category;
    const so = document.querySelector('#filter-form [name=sort]');
    if (so) so.value = state.filter.sort;
  }
};
