import { reactive } from 'vue';
import { createLegacyClient } from './client.js';
import { row, text, number } from './dto.js';
import { ApiError } from '../http/client.js';

/** @typedef {import('./dto.js').Row} Row 经过边界检查的旧对象。 */
const LIFETIME = 30 * 86400000;
/** 读取当前浏览器存储；受限浏览器保留内存行为，不抛出启动错误。 @param {string} key 名称。 @param {boolean} [temporary] 会话存储。 */
export function readStorage(key, temporary = false) {
  try {
    return (temporary ? sessionStorage : localStorage).getItem(key);
  } catch {
    return null;
  }
}
/** 写入或移除隔离存储；返回能否保存，让页面如实提示。 @param {string} key 名称。 @param {string|null} value 内容。 @param {boolean} [temporary] 会话存储。 */
export function writeStorage(key, value, temporary = false) {
  try {
    const storage = temporary ? sessionStorage : localStorage;
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}
/** 复用旧 Web 不透明会话与固定到期时间，不保存用户资料或口令。 */
function initialToken() {
  const token = readStorage('hc-token') || readStorage('hc-token', true) || '';
  const expiry = readStorage('hc-token-expires') || readStorage('hc-token-expires', true);
  return token && (!expiry || (Number.isFinite(Number(expiry)) && Number(expiry) > Date.now()))
    ? token
    : '';
}
export const session = reactive({
  token: initialToken(),
  me: /** @type {Row|null} */ (null),
  config: /** @type {Row} */ ({}),
  ready: false,
  epoch: 0,
  cart: /** @type {number[]} */ ([]),
  startupError: '',
  recoveryCode: '',
  listMemory: new Map(
    /** @type {[string,{items:Row[],page:number,exhausted:boolean,at:number}][]} */ ([]),
  ),
});
export const api = createLegacyClient({ token: () => session.token, expire: clearSession });
/** 清除私密内存与两种旧存储；当前页面随 epoch 重新挂载并中止旧任务。 */
export function clearSession() {
  session.listMemory.clear();
  session.recoveryCode = '';
  session.token = '';
  session.me = null;
  session.cart = [];
  session.epoch++;
  for (const temporary of [false, true]) {
    writeStorage('hc-token', null, temporary);
    writeStorage('hc-token-expires', null, temporary);
  }
}
/** 保存一次明确登录的结果，不因刷新身份接口延长浏览器会话。 @param {Row} result 登录结果。 */
export function acceptLogin(result) {
  session.listMemory.clear();
  session.recoveryCode = '';
  const token = text(result, 'token');
  const me = row(result.user);
  if (!token || !number(me, 'id')) throw new Error('登录响应缺少身份信息');
  session.me = me;
  session.token = token;
  session.epoch++;
  const expiry = String(Date.now() + LIFETIME);
  if (!writeStorage('hc-token-expires', expiry) || !writeStorage('hc-token', token)) {
    writeStorage('hc-token', null);
    writeStorage('hc-token-expires', null);
    writeStorage('hc-token', token, true);
    writeStorage('hc-token-expires', expiry, true);
  }
  restoreCart();
}
/** 只从当前账号的会话命名空间恢复清单，拒绝损坏与异常编号。 */
export function restoreCart() {
  try {
    const saved = JSON.parse(readStorage(`hc-cart-${number(session.me, 'id')}`, true) || '[]');
    session.cart = Array.isArray(saved)
      ? saved.filter((id) => Number.isSafeInteger(id) && id > 0).slice(0, 20)
      : [];
  } catch {
    session.cart = [];
  }
}
/** 修改按账号隔离的清单，跨卖家限制留给结算页与服务端核对。 @param {number} id 商品编号。 @param {boolean} [include] 是否加入。 */
export function changeCart(id, include = true) {
  if (!session.me) throw new Error('请先登录');
  if (include && !session.cart.includes(id)) {
    if (session.cart.length >= 20) throw new Error('一次最多选择 20 件商品');
    session.cart.push(id);
  }
  if (!include) session.cart = session.cart.filter((entry) => entry !== id);
  if (!include) {
    const key = `hc-vue-want-${number(session.me, 'id')}`;
    try {
      if (number(row(JSON.parse(readStorage(key, true) || '{}')), 'product') === id)
        writeStorage(key, null, true);
    } catch {
      writeStorage(key, null, true);
    }
  }
  writeStorage(`hc-cart-${number(session.me, 'id')}`, JSON.stringify(session.cart), true);
}
/** 初始化配置与实时身份，网络错误保留会话并提供重试，不回退虚构数据。 */
export async function initializeSession() {
  session.startupError = '';
  try {
    session.config = row(await api('/config'));
    if (session.token) {
      session.me = row(await api('/me'));
      restoreCart();
    }
  } catch (error) {
    // 换账号或会话过期属于身份转换，不能用旧请求错误遮住新的可用页面。
    if (
      !(error instanceof Error && error.name === 'AbortError') &&
      !(error instanceof ApiError && error.status === 401)
    )
      session.startupError = error instanceof Error ? error.message : '启动失败，请重试';
  } finally {
    session.ready = true;
  }
}
/** 跨标签退出或换账号时立即清私密内存，再从服务端确认新身份。 @param {StorageEvent} event 浏览器事件。 */
export function syncSession(event) {
  if (event.key !== 'hc-token' && event.key !== null) return;
  session.listMemory.clear();
  session.me = null;
  session.cart = [];
  session.epoch++;
  session.token = initialToken();
  void initializeSession();
}
/** 保留线上已有owner身份；群角色不构成平台权限，真实授权仍由后端核实。 @param {Row|null} [user] 当前身份。 */
export function roleRank(user = session.me) {
  return (
    { user: 0, support: 1, admin: 2, developer: 3, owner: 4 }[
      /** @type {'user'|'support'|'admin'|'developer'|'owner'} */ (text(user, 'role'))
    ] || 0
  );
}
