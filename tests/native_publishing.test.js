const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

let definition;
const storage = {};
const records = new Map();
const calls = [];
const app = {
  globalData: { user: { id: 4, nickname: '学生甲' }, sessionVersion: 0, baseURL: 'http://local' },
  async request(path, data) {
    calls.push({ path, data: data && JSON.parse(JSON.stringify(data)) });
    if (path === '/drafts') return [...records.values()];
    if (path.startsWith('/draft?id=')) return JSON.parse(JSON.stringify(records.get(path.split('=')[1])));
    if (path === '/draft') {
      const previous = records.get(data.id);
      if (previous && previous.version !== data.version) throw new Error('另一窗口已更新草稿');
      const result = { id: data.id, version: data.version + 1, fields: data.fields, photos: [], updated_at: 1234 };
      records.set(result.id, JSON.parse(JSON.stringify(result)));
      return result;
    }
    if (path === '/draft/publish') return { id: 66 };
    throw new Error('Unexpected API ' + path);
  },
};
const wx = {
  getStorageSync: key => storage[key],
  setStorageSync: (key, value) => { storage[key] = JSON.parse(JSON.stringify(value)); },
  removeStorageSync: key => { delete storage[key]; },
  showToast() {}, showModal() {}, navigateTo() {}, redirectTo() {},
  downloadFile: options => options.success({ statusCode: 200, tempFilePath: '/downloaded/private-image' }),
};
vm.runInNewContext(fs.readFileSync('web 7M/miniprogram/pages/publish/index.js', 'utf8'), {
  require:()=>({loadEditing:async()=>{throw new Error('not an edit scenario');}}), getApp: () => app, Page: value => { definition = value; }, wx, console,
  setTimeout, clearTimeout, Date, Math, Number, String, Object, JSON, Promise, Error,
});

function makePage() {
  return { ...definition, data: JSON.parse(JSON.stringify(definition.data)), setData(values) { Object.assign(this.data, values); } };
}

(async () => {
  assert.equal(typeof definition.saveDraft, 'function', 'Native publishing must support persistent drafts');
  const first = makePage();
  await first.onLoad({});
  first.input({ currentTarget: { dataset: { field: 'title' } }, detail: { value: '关窗教材' } });
  first.input({ currentTarget: { dataset: { field: 'price' } }, detail: { value: '12.50' } });
  await first.saveDraft();
  const saved = [...records.values()][0];
  assert.equal(saved.fields.title, '关窗教材');
  assert.equal(saved.fields.price, '12.50', 'Python must convert the monetary input to cents');
  assert.ok(saved.fields.notes.includes('未核对'));
  assert.ok(saved.fields.missing.includes('未核对'));
  assert.ok(saved.fields.accessories.includes('未核对'));
  first.onUnload();

  const resumed = makePage();
  await resumed.onLoad({ id: saved.id });
  assert.equal(resumed.data.fields.title, '关窗教材');
  assert.equal(resumed.data.fields.price, '12.50');
  resumed._failed.add('front');
  resumed.cache();
  resumed.onUnload();
  await resumed.onLoad({ id: saved.id });
  assert.ok(resumed._failed.has('front'), 'An interrupted replacement remains blocked after reopening');
  assert.ok(resumed.data.saveStatus.includes('重新选择'));
  resumed._failed.clear();
  resumed.cache();
  records.get(saved.id).version += 1;
  resumed.input({ currentTarget: { dataset: { field: 'title' } }, detail: { value: '旧窗口的修改' } });
  await resumed.saveDraft();
  assert.equal(resumed.data.conflict, true, 'Conflict must remain visible instead of overwriting newer data');
  assert.equal(records.get(saved.id).fields.title, '关窗教材');
  await resumed.copyDraft();
  assert.equal(resumed.data.conflict, false);
  assert.ok(calls.some(call => call.path === '/draft' && call.data.copy_from_id === saved.id));
  assert.ok([...records.values()].some(record => record.fields.title === '旧窗口的修改'));

  // The preview and submitted upload IDs must agree even when uploads finish out of order.
  const oldRequest = app.request.bind(app);
  const pendingUploads = [];
  app.request = (path, data) => path === '/upload' ? new Promise(resolve => pendingUploads.push({ resolve, data })) : oldRequest(path, data);
  let photoNumber = 0;
  wx.chooseMedia = options => options.success({ tempFiles: [{ tempFilePath: '/photo-' + (++photoNumber), size: 10 }] });
  wx.getFileSystemManager = () => ({ readFileSync: path => path });
  const firstPick = resumed.pick({ currentTarget: { dataset: { angle: 'front' } } });
  await new Promise(setImmediate);
  const secondPick = resumed.pick({ currentTarget: { dataset: { angle: 'front' } } });
  await new Promise(setImmediate);
  pendingUploads[1].resolve({ id: 'latest', angle: 'front', url: '/media/latest' });
  await secondPick;
  pendingUploads[0].resolve({ id: 'older', angle: 'front', url: '/media/older' });
  await firstPick;
  assert.equal(resumed.data.photos.front, '/photo-2');
  assert.equal(resumed.data.uploaded.front.id, 'latest', 'Slow stale upload must not replace the latest selection');
  app.request = oldRequest;

  // Dirty local changes must survive an independent server update while the editor is closed.
  resumed.input({ currentTarget: { dataset: { field: 'title' } }, detail: { value: '未同步的本机修改' } });
  clearTimeout(resumed._timer);
  const conflictId = resumed.data.draftId;
  const remote = records.get(conflictId);
  remote.version += 1;
  remote.fields.title = '其他窗口的新版';
  resumed._disposed = true;
  await resumed.onLoad({ id: conflictId });
  assert.equal(resumed.data.fields.title, '未同步的本机修改');
  assert.equal(resumed.data.conflict, true, 'A reopened stale cache must offer copy/reload instead of losing edits');

  const beforeSwitch = calls.filter(call => call.path === '/draft').length;
  app.globalData.user = { id: 5, nickname: '学生乙' };
  app.globalData.sessionVersion += 1;
  await resumed.saveDraft();
  assert.equal(calls.filter(call => call.path === '/draft').length, beforeSwitch, 'Old page must not post using the new account');
  records.clear();
  await resumed.onShow();
  assert.equal(resumed.data.fields.title, '');
  assert.equal(storage['zj-native-draft-4'], undefined, 'Account switch clears the old local private draft');
  resumed.onUnload();
  console.log('Native draft save, reload, unknown defaults, conflict copy and account isolation passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
