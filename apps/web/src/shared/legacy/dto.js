import { isRecord } from '../http/client.js';
/** @typedef {Record<string, unknown>} Row 旧 DTO，字段在读取处显式归一化。 */
/** 校验旧对象，拒绝 HTML、数组和不合法协议。 @param {unknown} value 外部值。 @returns {Row} */
export function row(value) {
  if (!isRecord(value)) throw new Error('业务数据格式不正确');
  return value;
}
/** 校验旧对象列表，不把协议错误当作空列表。 @param {unknown} value 外部值。 @returns {Row[]} */
export function rows(value) {
  if (!Array.isArray(value)) throw new Error('列表数据格式不正确');
  return value.map(row);
}
/** 提取显示文本，不使用不可信 HTML。 @param {Row|null|undefined} value 记录。 @param {string} key 字段。 @param {string} [fallback] 默认文案。 */
export function text(value, key, fallback = '') {
  const field = value?.[key];
  return typeof field === 'string' || typeof field === 'number' ? String(field) : fallback;
}
/** 提取有限数字，金额仍以整数分表示。 @param {Row|null|undefined} value 记录。 @param {string} key 字段。 */
export function number(value, key) {
  const field = value?.[key];
  return typeof field === 'number' && Number.isFinite(field) ? field : 0;
}
/** 读取可选嵌套对象列表；有值但类型错误仍抛出。 @param {Row|null|undefined} value 记录。 @param {string} key 字段。 */
export function children(value, key) {
  return value?.[key] == null ? [] : rows(value[key]);
}
/** 将整数分显示为两位元。 @param {number} cents 整数分。 */
export function money(cents) {
  return (cents / 100).toFixed(2);
}
/** 格式化服务端秒级时间。 @param {number} seconds Unix 秒。 */
export function date(seconds) {
  return seconds ? new Date(seconds * 1000).toLocaleString('zh-CN', { hour12: false }) : '待确认';
}
export const statusNames = {
  available: '在售',
  reserved: '已预留',
  sold: '已售出',
  removed: '已下架',
  awaiting_payment: '待付款',
  paid: '待交付',
  awaiting_handover: '待核对交接',
  awaiting_receipt: '待确认收货',
  completed: '已完成',
  cancelled: '已取消',
  disputed: '售后处理中',
  refunded: '已退款',
  partial_refunded: '部分退款',
  open: '待处理',
  processing: '处理中',
  review: '待复核',
  resolved: '已解决',
  pending: '待接受',
  accepted: '已接受',
  rejected: '已拒绝',
};
/** 显示业务状态，未知状态如实保留，不伪造已成功。 @param {string} status 原始状态。 */
export function statusLabel(status) {
  return /** @type {Record<string,string>} */ (statusNames)[status] || status;
}
