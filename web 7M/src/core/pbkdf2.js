'use strict';
// 客户端 PBKDF2-HMAC-SHA256。
//
// 为什么在这里（重要）
// --------------------
// Workers 免费计划只有 10ms CPU，Python 派生 600000 轮 PBKDF2 实测要
// 660ms 左右，必然触发 1102/超时。Cloudflare 的 WebCrypto deriveBits
// 又把生产环境的迭代数硬压在 100000，600k 不可用。浏览器里
// `window.crypto.subtle.deriveBits` 没有这个限制（Chrome/Edge/Firefox
// 都允许到 2^31-1），所以把这部分放到浏览器算：派生出的 digest 再走
// `/api/auth/login` 提交，服务端只做定长比较，不重新派生。
//
// 安全权衡（写在前面，避免后人在 review 时漏掉）
// ----------------------------------------------
// 把已派生好的 digest 直接提交 + 服务端存到 D1，意味着 D1 一旦泄漏，
// 攻击者拿到的是「已经跑完 600k 轮」的摘要，可以直接 pass-the-hash 登
// 录——不再需要去爆破明文。这把 PBKDF2 的价值从「给数据库加一道昂贵
// 的爆破门槛」降级为「只在网络传输链路上挡一道」。这是为了让
// Workers 免费计划能撑住试用版而做的妥协；等切到 Workers Paid 或自
// 有 KDF 服务时要立刻改回服务端派生，并在 commit message 里写明。
//
// 接口约定（与 `Backend mission/app/cloudflare/api.py` 对齐）
// ----------------------------------------------------------
//   pbkdf2Hex(password, saltHex, rounds, dkLen?)
//     -> Promise<string>          // 64 位十六进制摘要（默认 dkLen=32）
//   randomSaltHex() -> string     // 32 位十六进制盐（用于注册）

const DEFAULTS = {
  // 与 `crypto.ROUNDS` 对齐：600000。改这里要和后端同步改。
  rounds: 600000,
  dkLen: 32,
};

function subtleCrypto(){
  const c = window.crypto;
  if (!c || !c.subtle) throw new Error('当前浏览器不支持 SubtleCrypto（请用最新版 Chrome / Edge / Safari）');
  return c.subtle;
}

function hexToBytes(hex){
  if (!/^[0-9a-f]*$/i.test(hex) || hex.length % 2) throw new Error('盐或摘要不是合法的十六进制');
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

function bytesToHex(bytes){
  // 默认 toHex 用 Number.toString(16)，会丢前导 0 也不支持 256 以上的字节；
  // 手写循环最稳。
  let s = '';
  for (let i = 0; i < bytes.length; i++){
    const b = bytes[i];
    s += (b < 16 ? '0' : '') + b.toString(16);
  }
  return s;
}

async function importPasswordKey(subtle, password){
  const enc = new TextEncoder();
  return subtle.importKey(
    'raw',
    enc.encode(password),
    { name: 'PBKDF2' },
    false,
    ['deriveBits']
  );
}

export async function pbkdf2Hex(password, saltHex, rounds = DEFAULTS.rounds, dkLen = DEFAULTS.dkLen){
  if (typeof password !== 'string' || !password) throw new Error('口令为空');
  if (!Number.isInteger(rounds) || rounds < 10000) {
    // 下限与后端 `check_rounds` 保持一致；防止有人误把轮数调成 1 而不知。
    throw new Error('轮数过低，至少 10000；与后端 `crypto.ROUNDS` 同步');
  }
  if (!Number.isInteger(dkLen) || dkLen < 16 || dkLen > 64) throw new Error('摘要长度必须在 16–64 字节之间');
  const subtle = subtleCrypto();
  const key = await importPasswordKey(subtle, password);
  const bits = await subtle.deriveBits(
    {
      name: 'PBKDF2',
      // SHA-256 在所有主流浏览器实现里都可用；不强制 SHA-1/384/512。
      hash: 'SHA-256',
      salt: hexToBytes(saltHex),
      iterations: rounds,
    },
    key,
    dkLen * 8
  );
  return bytesToHex(new Uint8Array(bits));
}

export function randomSaltHex(){
  // 16 字节 = 32 位十六进制，与后端 `crypto.new_salt()` 等长。
  const bytes = subtleCrypto().getRandomValues(new Uint8Array(16));
  return bytesToHex(bytes);
}

export const PBKDF2_DEFAULTS = DEFAULTS;
