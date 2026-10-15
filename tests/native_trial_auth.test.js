const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
let definition,calls=[],stored={},notice='';
const app={globalData:{user:null,sessionVersion:0},request:async(path,data)=>{calls.push({path,data});return path==='/config'?{auth_mode:'password'}:{token:'test-session',user:{id:7,nickname:'同学',role:'user'},recovery_code:'fictional-recovery-code'};}};
const wx={setStorageSync:(key,value)=>stored[key]=value,getStorageSync:()=>null,removeStorageSync(){},showToast(){},showModal:options=>{notice=options.content;}};
vm.runInNewContext(fs.readFileSync('miniprogram/pages/hub/index.js','utf8'),{getApp:()=>app,Page:d=>definition=d,require:()=>require('../miniprogram/utils'),wx,console,setInterval,clearInterval,Date,Math,Number,Error});
const page={...definition,data:{...definition.data},setData(data){Object.assign(this.data,data);}};
(async()=>{
 assert.equal(page.data.authMode,'password','Until config loads, shared demo login must stay hidden');
 page.data.authView='register';
 await page.login({detail:{value:{phone:'13900000011',nickname:'同学',password:'StudentPassword2026!',password_confirm:'StudentPassword2026!',agree:['yes']}}});
 assert.ok(calls.some(call=>call.path==='/auth/register'),'Native trial registration must use password endpoint');
 assert.equal(stored['hc-token'],'test-session');
 assert.ok(notice.includes('fictional-recovery-code'),'Show recovery secret once to the account owner');
 assert.ok(!calls.some(call=>call.path==='/auth/code'));
 calls=[];page.data.authView='login';
 await page.login({detail:{value:{phone:'13900000011',password:'StudentPassword2026!'}}});
 assert.ok(calls.some(call=>call.path==='/auth/login'&&call.data.password==='StudentPassword2026!'));
 console.log('Native password registration/login/recovery notice passed; no shared-code request.');
})().catch(error=>{console.error(error);process.exitCode=1;});
