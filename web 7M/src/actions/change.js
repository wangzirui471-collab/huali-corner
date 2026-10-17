'use strict';
// 事件层 · change 事件（排序下拉、实拍图本地预览）

import { state } from '../core/state.js';
import { go } from '../core/nav.js';

export function registerChangeHandlers(){
  document.addEventListener('change', ev => {
    if (ev.target.id === 'sort-select'){ state.filter.sort = ev.target.value; state.homeLimit = 40; go('home'); }
    // 选好实拍图先在本地预览，真正上传要等发布表单提交。
    if (ev.target.type === 'file' && ['front','side','top'].includes(ev.target.name) && ev.target.files[0]){
      const preview = ev.target.closest('.upload-slot').querySelector('.upload-preview');
      preview.innerHTML = '';
      const img = document.createElement('img');
      img.src = URL.createObjectURL(ev.target.files[0]);
      img.onload = () => URL.revokeObjectURL(img.src);
      preview.appendChild(img);
    }
  });
}
