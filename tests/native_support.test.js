const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
let definition;
const calls = [];
const app = {
  globalData: { user: { id: 7, role: 'user' }, sessionVersion: 0 },
  async request(path, data) {
    calls.push({ path, data });
    if (path.startsWith('/ticket?id=')) return { id: 3, order_id: 9, type: 'refund', refund_mode: 'return_refund', user_id: 7, status: 'review', messages: [] };
    if (path.startsWith('/order?id=')) return { id: 9, buyer_id: 7, seller_id: 8, delivered_at: 1234 };
    if (path === '/relist') return { id: 'draft-after-return' };
    if (path === '/config') return { auth_mode: 'password' };
    return [];
  },
};
let navigate = '';
let pendingModal;
const wx = { showToast() {}, getStorageSync() {}, removeStorageSync() {},
  showModal(options) { pendingModal = options; }, navigateTo(options) { navigate = options.url; } };
vm.runInNewContext(fs.readFileSync('web 7M/miniprogram/pages/hub/index.js', 'utf8'), {
  getApp: () => app, Page: value => { definition = value; }, require: () => require('../web 7M/miniprogram/utils'),
  wx, console, setInterval, clearInterval, Date, Math, Number, String, Error, Promise,
});
const page = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), setData(values) { Object.assign(this.data, values); } };
(async () => {
  await page.openTicket({ currentTarget: { dataset: { id: 3 } } });
  assert.equal(page.data.activeTicketOrder.seller_id, 8, 'Returns require linked order and participant roles');
  assert.equal(page.data.canHandleTicket, false, 'Participants cannot act as staff on their case');
  page.returnAction({ currentTarget: { dataset: { action: 'return_sent' } } });
  await pendingModal.success({ confirm: true });
  assert.ok(calls.some(call => call.path === '/ticket/return' && call.data.id === 3 && call.data.action === 'return_sent'));
  await page.relist({ currentTarget: { dataset: { id: 6 } } });
  assert.equal(navigate, '/pages/publish/index?id=draft-after-return');
  page.returnAction({ currentTarget: { dataset: { action: 'return_sent' } } });
  app.globalData.user = { id: 8, role: 'user' };
  app.globalData.sessionVersion++;
  const before = calls.length;
  await pendingModal.success({ confirm: true });
  assert.equal(calls.length, before, 'Delayed confirmation must never submit using another account');
  page.clearPrivate();
  assert.equal(page.data.activeTicketOrder, null);
  assert.equal(page.data.creditHistory.length, 0);
  console.log('Native return roles, resale draft, delayed account switch and private cleanup passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
