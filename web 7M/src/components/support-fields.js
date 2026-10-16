export const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
export const names = { open: '待处理', processing: '处理中', review: '待复核', resolved: '已解决', available: '在售', reserved: '已预留', sold: '已售出', removed: '已下架' };
export const types = { refund: '售后', report: '举报', appeal: '申诉', other: '咨询', reschedule: '改约' };
export const field = (label, name, type = 'text', value = '', extra = '') => `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${e(value)}" ${extra}></label>`;
export const evidenceInput = '<label class="field"><span>图片证据（选填，每次最多6张）</span><input name="evidence" type="file" multiple accept="image/jpeg,image/png,image/webp"><small>请先遮挡手机号、证件等无关隐私，证据不会公开展示。</small></label>';
export const amountText = cents => (cents / 100).toFixed(2);


