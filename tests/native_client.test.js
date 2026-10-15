const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const app={globalData:{user:{id:3,role:'admin'},sessionVersion:0},request:async()=>[]};let def;
const wx={removeStorageSync(){},getStorageSync(){return null},showToast(){}};
vm.runInNewContext(fs.readFileSync('miniprogram/pages/hub/index.js','utf8'),{getApp:()=>app,Page:d=>def=d,require:()=>require('../miniprogram/utils'),wx,console,setInterval,clearInterval,Date,Math,Number});
const page={...def,data:{...def.data,user:app.globalData.user,orders:[{id:123}],tickets:[{id:4}],activeTicket:{body:'STAFF ONLY',messages:[{internal:1,body:'secret'}]},rooms:[{id:7}],messages:[{body:'private'}],cart:[{id:1}],products:[]},setData(d){Object.assign(this.data,d);}};
page.logout();
for(const key of ['orders','tickets','rooms','messages','cart'])assert.equal(page.data[key].length,0,'Logout must clear '+key);
assert.equal(page.data.activeTicket,null,'Logout must clear staff ticket evidence');
assert.equal(page.data.currentRoom,0,'Logout must clear private room');
console.log('Native client privacy checks passed');

(async()=>{page.data.currentRoom=7;page.data.messages=[];let seen=[];app.request=async p=>{seen.push(p);return p.includes('after=100')?[{id:101,body:'new'}]:Array.from({length:100},(_,i)=>({id:i+1,body:'old'}));};await page.loadMessages();await page.loadMessages();assert.equal(page.data.messages.length,101);assert.ok(seen[1].includes('after=100'));console.log('Native chat cursor checks passed');})().catch(e=>{console.error(e);process.exitCode=1;});
let appDefinition,pending;
vm.runInNewContext(fs.readFileSync('miniprogram/app.js','utf8'),{App:d=>appDefinition=d,wx:{getStorageSync:()=>'',request:o=>{pending=o;}},Promise,Error});
appDefinition.globalData.sessionVersion=0;
const outstanding=appDefinition.request('/tickets');
appDefinition.globalData.sessionVersion=1;
pending.success({statusCode:200,data:[{body:'old account data'}]});
outstanding.then(()=>{throw new Error('Old account response must not resolve');},()=>console.log('Native in-flight account switch check passed')).catch(e=>{console.error(e);process.exitCode=1;});
