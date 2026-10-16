const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
let definition;
const calls=[];
const app={globalData:{user:{id:7},sessionVersion:0},request:async(path,data)=>{
  calls.push({path,data});
  if(path==='/config')return{buildings:['C1','C2','B9']};
  return [];
}};
const wx={showToast(){},getStorageSync:()=>[],showModal(){}};
vm.runInNewContext(fs.readFileSync('miniprogram/pages/hub/index.js','utf8'),{
  Page:value=>definition=value,getApp:()=>app,require:()=>require('../miniprogram/utils'),
  wx,console,Date,Math,Number,String,Error,Promise,setInterval,clearInterval,
});
const page={...definition,data:JSON.parse(JSON.stringify(definition.data)),setData(values){Object.assign(this.data,values);}};
(async()=>{
  page.onLoad({tab:'orders'});
  await page.load();
  assert.equal(page.data.buildingChoices[1],'C1');
  page.data.orders=[{id:33,location:'A1公共入口',appointment:Date.now()/1000+7200}];
  page.propose({currentTarget:{dataset:{id:33}}});
  assert.equal(page.data.rescheduleId,33,'Native reschedule must expose editable building/location fields');
  page.rescheduleBuilding({detail:{value:'2'}});
  assert.equal(page.data.rescheduleAddress,'C2楼下公共入口');
  page.rescheduleAddressInput({detail:{value:'图书馆南门公共等候区'}});
  await page.rescheduleSubmit();
  const request=calls.find(call=>call.path==='/order/action');
  assert.equal(request.data.action,'reschedule');
  assert.equal(request.data.address,'图书馆南门公共等候区');
  assert.ok(request.data.appointment>Date.now()/1000);
  page.checkoutBuilding({detail:{value:'3'}});
  assert.equal(page.data.checkoutAddress,'B9楼下公共入口');
  console.log('Native building selection and custom locations for checkout/reschedule passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
