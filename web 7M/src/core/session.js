'use strict';
// Persist only the opaque session token; the server always verifies identity and roles.
const TOKEN = 'hc-token';
const EXPIRES = 'hc-token-expires';
const LIFETIME = 30 * 86400000;
const localListeners = new Set();

/** 同页登录或退出立即通知私密面板清理；跨页变化仍沿用 storage 监听。 */
function announceSession(token){
  for (const listener of localListeners) listener(token);
}

function store(kind){ try { return globalThis[kind]; } catch { return null; } }
function get(storage, key){ try { return storage?.getItem(key); } catch { return null; } }
function remove(storage){
  for (const key of [TOKEN, EXPIRES]){ try { storage?.removeItem(key); } catch {} }
}

export function forgetSession(){
  remove(store('localStorage'));
  remove(store('sessionStorage'));
  announceSession('');
}

export function rememberSession(token){
  if (!token){ forgetSession(); return; }
  const expires = String(Date.now() + LIFETIME);
  const local = store('localStorage'), session = store('sessionStorage');
  try {
    local.setItem(EXPIRES, expires);
    local.setItem(TOKEN, token);
    remove(session);
  } catch {
    remove(local);
    try { session.setItem(EXPIRES, expires); session.setItem(TOKEN, token); } catch {}
  }
  announceSession(token);
}

export function readSessionToken(now = Date.now()){
  const local = store('localStorage'), session = store('sessionStorage');
  const token = get(local, TOKEN) || get(session, TOKEN) || '';
  if (!token) return '';
  const rawExpiry = get(local, TOKEN) ? get(local, EXPIRES) : get(session, EXPIRES);
  const expires = Number(rawExpiry);
  if (rawExpiry != null && (!Number.isFinite(expires) || expires <= now)){
    forgetSession(); return '';
  }
  // Migrate the previous tab-only login. This never extends server-side expiry.
  if (!get(local, TOKEN) && !get(session, EXPIRES)) rememberSession(token);
  return token;
}

export function subscribeSession(onChange){
  // 已有订阅同时接收本页变化，避免只在另一标签页退出时才清理。
  localListeners.add(onChange);
  const onStorage = event => {
    if (event.key !== TOKEN && event.key !== null) return;
    // A stale tab-only token must not resurrect an account logged out elsewhere.
    remove(store('sessionStorage'));
    onChange(readSessionToken());
  };
  window.addEventListener('storage', onStorage);
  return () => {
    localListeners.delete(onChange);
    window.removeEventListener?.('storage', onStorage);
  };
}
