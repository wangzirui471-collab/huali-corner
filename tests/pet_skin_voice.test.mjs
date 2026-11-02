// 龙娘（GPT 娘）姿势皮肤 + 语音朗读的自检。
// 运行：node tests/pet_skin_voice.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const POSE_DIR = path.join(ROOT, 'web 7M', 'assets', 'ai-pet', 'gpt', 'poses');

const store = {};
globalThis.window = { HUALI_STATIC_DEMO: false, addEventListener(){}, scrollTo(){}, innerWidth: 1200, innerHeight: 900 };
globalThis.sessionStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
};
globalThis.document = {
  querySelector: () => null, querySelectorAll: () => [], addEventListener(){},
  createElement: () => ({ appendChild(){}, classList: { add(){}, remove(){}, toggle(){} } }),
  documentElement: { style: { setProperty(){} } },
};
globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: 'mock' }) });
globalThis.location = { hash: '', href: 'http://localhost/' };

const { SKINS, SKIN_LIST, DEFAULT_SKIN, resolveAct, festivalAct, getSkinId } =
  await import('../web 7M/src/components/pet-skins.js');
const { cleanForSpeech, chunkForSpeech, getVoiceRate, setVoiceRate, getVoiceOn, setVoiceOn, speak, voiceSupported } =
  await import('../web 7M/src/components/pet-voice.js');

test('龙娘皮肤：姿势模式、动作齐全、每个姿势文件都在仓库里', () => {
  const skin = SKINS.gpt;
  assert.equal(skin.mode, 'poses');
  assert.equal(skin.name, '小转');
  assert.ok(skin.note.includes('龙娘'));
  assert.equal(DEFAULT_SKIN, 'gpt');
  assert.equal(SKIN_LIST[0].id, 'gpt', '龙娘排第一位');
  for (const act of ['idle', 'idle2', 'idle3', 'blink', 'greet', 'look', 'lie', 'think', 'write', 'fail', 'move', 'moveLeft', 'pat']){
    assert.ok(skin.acts[act], `缺动作 ${act}`);
  }
  // 姿势文件要真的存在：路径写错只会变成空白桌宠，测试必须先拦住。
  for (const act of Object.values(skin.acts)){
    const rel = act.src.replace('/assets/ai-pet/gpt/poses/', '');
    assert.ok(fs.existsSync(path.join(POSE_DIR, rel)), `缺文件 ${rel}`);
  }
  for (const file of Object.values(skin.seasonal)){
    assert.ok(fs.existsSync(path.join(POSE_DIR, file)), `缺节日图 ${file}`);
  }
  assert.ok(fs.existsSync(path.join(ROOT, 'web 7M', 'assets', 'ai-pet', 'gpt', 'ATTRIBUTION.md')), '缺授权说明');
});

test('状态映射：打字/思考走龙娘专属动作，图集皮肤不受影响', () => {
  const gpt = SKINS.gpt;
  assert.equal(resolveAct(gpt, 'typing').act, 'write');
  assert.equal(resolveAct(gpt, 'review').act, 'think');
  assert.equal(resolveAct(gpt, 'point').act, 'look');
  // 大乔没有 think/write，仍走原来的 lie。
  assert.equal(resolveAct(SKINS.daqiao, 'review').act, 'lie');
  assert.equal(resolveAct(SKINS.daqiao, 'typing').act, 'lie');
});

test('节日装扮：春节窗口命中，平日不命中', () => {
  assert.equal(festivalAct(SKINS.gpt, new Date('2026-02-18T10:00:00')), 'seasonal');
  assert.equal(festivalAct(SKINS.gpt, new Date('2026-10-03T10:00:00')), 'seasonal');   // 国庆
  assert.equal(festivalAct(SKINS.gpt, new Date('2026-08-01T10:00:00')), '');
  assert.equal(festivalAct(SKINS.daqiao, new Date('2026-02-18T10:00:00')), '');        // 图集皮肤没有节日图
});

test('语音文本清洗：Markdown、链接、表情都读不出来', () => {
  const out = cleanForSpeech('**发布** 的步骤：\n1. 点 [这里](https://a.b) 🎉\n`code`');
  assert.ok(!out.includes('*'), out);
  assert.ok(!out.includes('http'), out);
  assert.ok(!out.includes('🎉'), out);
  assert.ok(out.includes('发布'), out);
  assert.deepEqual(chunkForSpeech('好。'.repeat(120)).length > 1, true, '长句要切开');
});

test('语速与开关：范围受限，写进 localStorage', () => {
  setVoiceRate(3);
  assert.equal(getVoiceRate(), 1.4);
  setVoiceRate(.2);
  assert.equal(getVoiceRate(), .8);
  setVoiceOn(false);
  assert.equal(getVoiceOn(), false);
  // Node 里没有 speechSynthesis：speak 应该安静地返回 false，不能抛错。
  assert.equal(voiceSupported(), false);
  assert.equal(speak('你好'), false);
});
