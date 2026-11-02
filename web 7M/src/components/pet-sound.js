'use strict';
// 桌宠点击音效
//
// 桌面版用的是素材目录里的 click.wav；网页这版不额外放音频文件，
// 直接用 WebAudio 合成一个 90ms 的下滑短音（"啵"）。好处是没有网络请求、
// 不需要用户手势之外的权限，命中率和素材版听感接近。
//
// 浏览器要求首次发声在用户手势里：点击本身是手势，所以第一次点就会初始化。

const KEY = 'hc-pet-sound';
let ctx = null;

export function getSoundOn(){
  try{ return localStorage.getItem(KEY) !== '0'; }catch(_){ return true; }
}

export function setSoundOn(on){
  try{ localStorage.setItem(KEY, on ? '1' : '0'); }catch(_){ /* 隐私模式：本次生效 */ }
}

export function playPetClick(){
  if (!getSoundOn()) return false;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return false;
  try{
    ctx = ctx || new AC();
    if (ctx.state === 'suspended') ctx.resume();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(920, t);
    osc.frequency.exponentialRampToValueAtTime(430, t + .085);
    gain.gain.setValueAtTime(.0001, t);
    gain.gain.exponentialRampToValueAtTime(.08, t + .012);
    gain.gain.exponentialRampToValueAtTime(.0001, t + .12);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t);
    osc.stop(t + .14);
    return true;
  }catch(_){ return false; }
}
