'use strict';
// 组件层 · 表单字段
// field() 的 extra 用来塞 required / maxlength / placeholder 之类的原生属性。

import { e } from '../core/dom.js';

export function field(label, name, type='text', value='', extra=''){
  return `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${e(value)}" ${extra}></label>`;
}

export function selectField(label, name, opts){
  return `<label class="field"><span>${label}</span><select name="${name}">${opts.map(v=>`<option value="${e(Array.isArray(v)?v[0]:v)}">${e(Array.isArray(v)?v[1]:v)}</option>`).join('')}</select></label>`;
}
