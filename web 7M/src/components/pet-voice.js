'use strict';
// 桌宠语音 · 朗读回答与台词
//
// 用浏览器自带的 Web Speech API（speechSynthesis），不额外接云端 TTS：
//   · 不产生费用、不需要密钥，离线也能发声；
//   · 音色和语速由系统语音库决定，Chrome/Edge 在 Windows 上一般都有中文女声；
//   · 长句要自己切：Chrome 对单条 utterance 有 15 秒上限，整段丢进去会在中途静音。
//
// 设置面板只读写偏好，真正发声由 ai-pet.js / actions/support.js 调用 speak()。

const ON_KEY = 'hc-pet-voice';
const VOICE_KEY = 'hc-pet-voice-name';
const RATE_KEY = 'hc-pet-voice-rate';

function read(key, fallback){
  try{
    const v = localStorage.getItem(key);
    return v === null ? fallback : v;
  }catch(_){ return fallback; }
}

function write(key, val){
  try{ localStorage.setItem(key, val); }catch(_){ /* 隐私模式：本次生效即可 */ }
}

export function voiceSupported(){
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
}

export function getVoiceOn(){ return read(ON_KEY, '1') !== '0'; }
export function setVoiceOn(on){ write(ON_KEY, on ? '1' : '0'); if (!on) stopSpeaking(); }

// 语速 0.8–1.4：再快中文听不清，再慢一句能拖十秒。
export function getVoiceRate(){
  const v = Number(read(RATE_KEY, '1'));
  return Number.isFinite(v) ? Math.min(1.4, Math.max(.8, v)) : 1;
}
export function setVoiceRate(v){ write(RATE_KEY, String(Math.min(1.4, Math.max(.8, Number(v) || 1)))); }

export function getVoiceName(){ return read(VOICE_KEY, ''); }
export function setVoiceName(name){ write(VOICE_KEY, String(name || '')); }

let voices = [];
let primed = false;

function refreshVoices(){
  if (!voiceSupported()) return voices;
  const list = window.speechSynthesis.getVoices() || [];
  if (list.length) voices = list;
  return voices;
}

/** 语音列表是异步加载的：第一次拿不到就等 voiceschanged 再回调一次。 */
export function primeVoices(onReady){
  if (!voiceSupported()) return;
  refreshVoices();
  if (primed) { onReady?.(voices); return; }
  primed = true;
  window.speechSynthesis.addEventListener?.('voiceschanged', () => {
    refreshVoices();
    onReady?.(voices);
  });
  // Safari 老版本只有 onvoiceschanged 回调，不派发事件。
  window.speechSynthesis.onvoiceschanged = () => { refreshVoices(); onReady?.(voices); };
  onReady?.(voices);
}

/** 中文语音排前面，其余按语言分组；返回给设置面板的下拉用。 */
export function listVoices(){
  refreshVoices();
  const score = v => (/^zh/i.test(v.lang || '') ? 0 : /^en/i.test(v.lang || '') ? 1 : 2);
  return [...voices]
    .sort((a, b) => score(a) - score(b) || String(a.name).localeCompare(String(b.name)))
    .map(v => ({ name: v.name, lang: v.lang || '', local: !!v.localService }));
}

function pickVoice(){
  if (!voices.length) refreshVoices();
  const name = getVoiceName();
  const hit = voices.find(v => v.name === name);
  if (hit) return hit;
  return voices.find(v => /^zh/i.test(v.lang || '')) || voices[0] || null;
}

// --- 文本处理 ---------------------------------------------------------
// 回答里会有 Markdown 符号、链接、编号和表情：读出来之前必须先洗掉，
// 否则会听到「星号星号」「左括号」「http 冒号斜杠斜杠」。
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}]/gu;

export function cleanForSpeech(text){
  return String(text ?? '')
    .replace(/```[\s\S]*?```/g, '，代码略，')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '链接')
    .replace(/^[#>]+\s*/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/[*_~]{1,2}/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(EMOJI, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

/** 按标点切句，单条不超过 110 字：Chrome 的长句上限是按时间算的，切短最稳。 */
export function chunkForSpeech(text, max = 110){
  const clean = cleanForSpeech(text);
  if (!clean) return [];
  const parts = clean.split(/(?<=[。！？!?；;\n])/);
  const out = [];
  let buf = '';
  for (const raw of parts){
    const piece = raw.trim();
    if (!piece) continue;
    if ((buf + piece).length <= max){ buf += piece; continue; }
    if (buf) out.push(buf);
    if (piece.length <= max){ buf = piece; continue; }
    // 还是太长：按逗号再切，最后按硬长度切。
    for (const sub of piece.split(/(?<=[，,、：:])/)){
      const s = sub.trim();
      if (!s) continue;
      if ((buf + s).length <= max) buf += s;
      else { if (buf) out.push(buf); buf = s.slice(0, max); }
    }
  }
  if (buf) out.push(buf);
  return out;
}

let speaking = false;

export function stopSpeaking(){
  if (!voiceSupported()) return;
  try{ window.speechSynthesis.cancel(); }catch(_){ }
  speaking = false;
}

/**
 * 朗读一段文字。返回 false 表示没读（关闭、不支持、没内容）。
 * force=true 用于「试听」，忽略关闭开关。
 */
export function speak(text, { force = false } = {}){
  if (!voiceSupported()) return false;
  if (!force && !getVoiceOn()) return false;
  const chunks = chunkForSpeech(text);
  if (!chunks.length) return false;
  try{ window.speechSynthesis.cancel(); }catch(_){ }
  const voice = pickVoice();
  const rate = getVoiceRate();
  speaking = true;
  chunks.forEach((chunk, index) => {
    const u = new SpeechSynthesisUtterance(chunk);
    u.lang = voice?.lang || 'zh-CN';
    if (voice) u.voice = voice;
    u.rate = rate;
    u.pitch = 1;
    if (index === chunks.length - 1) u.onend = () => { speaking = false; };
    u.onerror = () => { speaking = false; };
    window.speechSynthesis.speak(u);
  });
  return true;
}

export function isSpeaking(){ return speaking; }
