const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
let app;
let pending;
let timer;
const storage = {'hc-token':'test-token'};
const wx = {getStorageSync:key=>storage[key], request:options=>{pending=options;}};
vm.runInNewContext(fs.readFileSync('miniprogram/app.js','utf8'), {
  App: value=>{app=value;}, wx, Promise, Error, Set, Number,
  setInterval:fn=>{timer=fn;return 1;}, clearInterval:()=>{timer=null;},
});
(async()=>{
  assert.equal(typeof app.startNotifications,'function','App must refresh account-owned unread alerts');
  app.globalData.user={id:7};
  let count=-1;
  const unsubscribe=app.watchNotifications(value=>{count=value;});
  app.startNotifications();
  pending.success({statusCode:200,data:{unread_count:3,items:[],latest_id:7}});
  await new Promise(setImmediate);
  assert.equal(app.globalData.notificationCount,3);
  assert.equal(count,3);
  timer();
  const oldPending=pending;
  app.globalData.sessionVersion++;
  app.globalData.user={id:8};
  app.stopNotifications();
  oldPending.success({statusCode:200,data:{unread_count:99,items:[],latest_id:99}});
  await new Promise(setImmediate);
  assert.equal(app.globalData.notificationCount,0,'Late old-account unread state must not reappear');
  unsubscribe();
  console.log('Native app unread polling, listeners, stop and in-flight account isolation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
