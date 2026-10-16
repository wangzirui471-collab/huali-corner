const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const calls=[],storage=new Map([['zj-native-draft-7','x'],['zj-native-edit-7-2','x'],['zj-native-draft-8','other']]);
const app={globalData:{user:{id:7},sessionVersion:1},async request(path,data){calls.push({path,data});if(path.startsWith('/messages?'))return [{id:3,body:'你好'}];if(path==='/rooms')return {joined:[]};return {};}};
const wx={getStorageInfoSync:()=>({keys:[...storage.keys()]}),removeStorageSync:key=>storage.delete(key)};
function load(file){const module={exports:{}};vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,getApp:()=>app,wx,Set,Math,Number});return module.exports;}
(async()=>{
 const chat=load('web 7M/miniprogram/features/chat.js');
 const page={...chat,data:{tab:'messages',currentRoom:2,messages:[]},identity:()=>()=>true,setData(v){Object.assign(this.data,v);},error(e){throw e;}};
 await page.loadMessages();
 assert.ok(calls.some(c=>c.path==='/messages/read'&&c.data.through_id===3));
 const cleanup=load('web 7M/miniprogram/features/account-cache.js');cleanup.clearDeviceCopies(7);
 assert.equal(storage.has('zj-native-edit-7-2'),false);assert.equal(storage.get('zj-native-draft-8'),'other');
 console.log('Native message read cursor and account-owned device cleanup passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
