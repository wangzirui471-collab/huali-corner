import { e as escape } from '../core/dom.js';
export { escape };
export const input = (label, name, value = '', attributes = '') => `<label class="field"><span>${label}</span><input name="${name}" value="${escape(value)}" ${attributes}></label>`;
export const select = (label, name, options, value) => `<label class="field"><span>${label}</span><select name="${name}">${options.map(option => {
    const [key, text] = Array.isArray(option) ? option : [option, option];
    return `<option value="${escape(key)}" ${key === value ? 'selected' : ''}>${escape(text)}</option>`;
  }).join('')}</select></label>`;


