const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const calls=[];let definition,navigation='';
const post={id:6,user_id:7,kind:'need',service_type:'parcel',service_label:'快递代取',title:'取件',body:'取件码私聊',reward:250,place:'C1楼下',deadline:Date.now()/1000+7200,status:'open'};
const app={globalData:{user:{id:7},sessionVersion:1},async request(path,data){calls.push({path,data});if(path.startsWith('/help/posts?'))return {items:[post],next_cursor:null,has_more:false};if(path==='/rooms/private')return {id:8};return post;}};
const wx={showToast(){},navigateTo(options){navigation=options.url;}};
vm.runInNewContext(fs.readFileSync('web 7M/miniprogram/pages/help/index.js','utf8'),{getApp:()=>app,Page:value=>definition=value,require:()=>require('../web 7M/miniprogram/utils'),wx,Date,Math,Number});
const page={...definition,data:{...definition.data},setData(values){Object.assign(this.data,values);}};
(async()=>{
 page.onLoad({});await page.load();assert.equal(page.data.items[0].rewardText,'意向报酬 ¥2.50');
 page.publish();page.pickType({detail:{value:'0'}});
 await page.submit({detail:{value:{title:'取件',body:'说明',reward_yuan:'2.50',place:'C1楼下'}}});
 const publish=calls.find(call=>call.path==='/help/posts');assert.equal(publish.data.service_type,'parcel');assert.equal(publish.data.kind,'need');assert.ok(publish.data.deadline>Date.now()/1000);
 await page.contact({currentTarget:{dataset:{user:'9'}}});assert.equal(navigation,'/pages/hub/index?tab=messages&room=8');
 assert.ok(!calls.some(call=>/checkout|payment|settlement/.test(call.path)));
 app.globalData.user=null;page.publish();assert.equal(navigation,'/pages/hub/index?tab=me');
 console.log('Native help bulletin publishing, contact, money display and login guard passed; no service payment calls.');
})().catch(error=>{console.error(error);process.exitCode=1;});
