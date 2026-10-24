import { api, session, acceptLogin, clearSession } from '@/shared/legacy/session.js';
import { row, text, number } from '@/shared/legacy/dto.js';

/** 使用标准 WebCrypto 兼容旧客户端派生协议；新凭据固定 600000 轮。 @param {string} password 口令。 @param {string} salt 十六进制盐。 @param {number} rounds 服务端已有轮数。 */
export async function derivePassword(password, salt, rounds) {
  if (!/^(?:[0-9a-f]{2})+$/i.test(salt) || !Number.isSafeInteger(rounds) || rounds < 10000)
    throw new Error('服务端口令参数不合法');
  if (!globalThis.crypto?.subtle)
    throw new Error('请在 HTTPS 或 localhost 使用支持 WebCrypto 的浏览器');
  const bytes = Uint8Array.from(salt.match(/../g) || [], (hex) => parseInt(hex, 16));
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  const result = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt: bytes, iterations: rounds },
    key,
    256,
  );
  return Array.from(new Uint8Array(result), (value) => value.toString(16).padStart(2, '0')).join(
    '',
  );
}
/** 新凭据使用随机盐，不采用固定盐或较低轮数。 @param {string} password 新口令。 */
export async function newCredential(password) {
  const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
  return { salt, rounds: 600000, digest: await derivePassword(password, salt, 600000) };
}
/** 登录只兼容服务器明确公布的密码模式；不引入共享默认口令。 @param {string} phone 账号。 @param {string} password 口令。 @param {typeof api} [request] 页面请求边界。 */
export async function login(phone, password, request = api) {
  let credentials = /** @type {Record<string, unknown>} */ ({ phone, password });
  if (text(session.config, 'auth_mode') === 'client_kdf') {
    const salt = row(await request(`/auth/salt?phone=${encodeURIComponent(phone)}`));
    credentials = {
      phone,
      digest: await derivePassword(password, text(salt, 'salt'), number(salt, 'rounds')),
    };
  }
  acceptLogin(row(await request('/auth/login', { body: credentials })));
}
/** 注册保留学院/年级/专业字段；恢复码仅由页面一次展示。 @param {{phone:string,password:string,nickname:string,college:string,grade:string,major:string}} form 注册数据。 @param {typeof api} [request] 页面请求边界。 */
export async function register(form, request = api) {
  const { password, ...profile } = form;
  const credential =
    text(session.config, 'auth_mode') === 'client_kdf'
      ? await newCredential(password)
      : { password };
  const result = row(await request('/auth/register', { body: { ...profile, ...credential } }));
  acceptLogin(result);
  session.recoveryCode = text(result, 'recovery_code');
  return text(result, 'recovery_code');
}
/** 密码修改或恢复后旧会话全部失效，恢复码不进入持久存储。 @param {{phone:string,new_password:string,recovery_code?:string,old_password?:string}} form 口令资料。 @param {boolean} [change] 是否已登录改密。 @param {typeof api} [request] 页面请求边界。 */
export async function resetPassword(form, change = false, request = api) {
  let body = /** @type {Record<string, unknown>} */ ({ ...form });
  if (text(session.config, 'auth_mode') === 'client_kdf') {
    body = {
      phone: form.phone,
      recovery_code: form.recovery_code,
      ...(await newCredential(form.new_password)),
    };
    if (change) {
      const salt = row(await request('/auth/salt'));
      body.old_digest = await derivePassword(
        form.old_password || '',
        text(salt, 'salt'),
        number(salt, 'rounds'),
      );
    }
  }
  const result = row(await request(change ? '/auth/password' : '/auth/recover', { body }));
  clearSession();
  session.recoveryCode = text(result, 'recovery_code');
  return text(result, 'recovery_code');
}
