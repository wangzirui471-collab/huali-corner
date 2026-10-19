'use strict';
// 基础设施层 · 登录令牌的本地持久化
//
// 用户要求（2026-10）：一个账号在这台电脑上登录过，下次打开就不用再登录。
// 因此令牌存 localStorage（关浏览器仍保留），不再只存 sessionStorage。
//
// 安全边界（与后端配合）：
//   · 后端会话 30 天有效，且每次访问时剩余不足 7 天自动续满 30 天；
//     闲置超过 30 天会失效，不是永久令牌；
//   · 退出登录 / 注销账号 / 改密找回都会清掉本地令牌；
//   · 共用电脑时请用「退出登录」——页面上一直有这个入口。
//
// 兼容：老版本把令牌存在 sessionStorage 里，这里读的时候一并认，
// 读到后由 saveToken 迁移到 localStorage。

const KEY = 'hc-token';

function store(kind){
  try{ return kind === 'local' ? window.localStorage : window.sessionStorage; }catch{ return null; }
}

export function readToken(){
  const local = store('local');
  const session = store('session');
  try{
    const token = (local && local.getItem(KEY)) || (session && session.getItem(KEY)) || '';
    if (token && local && !local.getItem(KEY)) local.setItem(KEY, token);   // 旧会话迁移
    return token;
  }catch{ return ''; }
}

export function saveToken(token){
  const local = store('local');
  const session = store('session');
  try{
    if (local) local.setItem(KEY, token);
    if (session) session.removeItem(KEY);   // 迁移完成，清掉旧位置，避免两份不一致
  }catch{}
}

export function clearToken(){
  for (const kind of ['local', 'session']){
    const s = store(kind);
    try{ if (s) s.removeItem(KEY); }catch{}
  }
}
