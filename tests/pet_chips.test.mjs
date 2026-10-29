// 桌宠「快捷指令」的收起/展开：工作模式 14 个按钮铺满四五行走廊，
// 收起来后要能记住，重开面板、切模式、刷新都不能自己弹回来。
// 运行：node tests/pet_chips.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const store = {};
globalThis.window = { HUALI_STATIC_DEMO: false, addEventListener() {}, scrollTo() {}, innerWidth: 1200, innerHeight: 900 };
globalThis.sessionStorage = { getItem: () => null, setItem() {}, removeItem() {} };
globalThis.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
};
// 只实现 $() 需要的 querySelector：按 #id 返回可写的假节点。
const nodes = {};
const node = id => (nodes[id] ||= {
  id, hidden: false, textContent: '', attrs: {},
  setAttribute(k, v) { this.attrs[k] = v; },
});
globalThis.document = {
  querySelector: sel => (sel.startsWith('#') ? node(sel.slice(1)) : null),
  querySelectorAll: () => [],
  addEventListener() {},
  createElement: () => ({ appendChild() {}, classList: { add() {}, remove() {}, toggle() {} } }),
  documentElement: { style: { setProperty() {} } },
};
globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: 'mock' }) });
globalThis.location = { hash: '', href: 'http://localhost/' };
try {
  Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText: async () => {} } }, configurable: true });
} catch { /* 已经有 navigator 就用现成的 */ }

const { state } = await import(new URL('../web 7M/src/core/state.js', import.meta.url));
const { applyPetChips, togglePetChips } = await import(new URL('../web 7M/src/components/ai-pet.js', import.meta.url));

const head = () => node('ai-pet-chips-head');
const faq = () => node('ai-pet-faq-chips');
const office = () => node('ai-pet-office-chips');
const work = () => node('ai-pet-work-chips');
const toggle = () => node('ai-pet-chips-toggle');

test('普通用户看不到模式页签和快捷指令', () => {
  state.me = { id: 2, role: 'user' };
  applyPetChips('work');
  assert.equal(head().hidden, true);
  assert.equal(work().hidden, true);
});

test('所有者首次进工作模式：指令展开，客服常见问让位', () => {
  state.me = { id: 1, role: 'owner' };
  applyPetChips('work');
  assert.equal(head().hidden, false);
  assert.equal(work().hidden, false, '工作指令应展开');
  assert.equal(office().hidden, true, '办公指令不该同时出现');
  assert.equal(faq().hidden, true, '工作模式下客服常见问先让位');
  assert.equal(toggle().textContent, '收起');
  assert.equal(toggle().attrs['aria-expanded'], 'true');
});

test('收起后记账，切模式不会把行又打开', () => {
  togglePetChips('work');
  assert.equal(work().hidden, true);
  assert.equal(toggle().textContent, '展开');
  assert.equal(toggle().attrs['aria-expanded'], 'false');
  assert.equal(store['hc-pet-chips-collapsed'], '1');

  applyPetChips('chat');
  assert.equal(faq().hidden, false, '回到客服问答要恢复常见问');
  assert.equal(head().hidden, true);
  applyPetChips('work');
  assert.equal(work().hidden, true, '重新进工作模式仍应保持收起');
  assert.equal(toggle().textContent, '展开');
});

test('刷新页面后仍记得收起状态，再点一次能展开', () => {
  applyPetChips('chat');
  applyPetChips('work');                 // 等价于刷新后重新挂载
  assert.equal(work().hidden, true);

  togglePetChips('work');
  assert.equal(work().hidden, false);
  assert.equal(store['hc-pet-chips-collapsed'], '0');

  togglePetChips('office');              // 办公和工作共用同一个开关
  assert.equal(office().hidden, true);
  assert.equal(work().hidden, true);
});
