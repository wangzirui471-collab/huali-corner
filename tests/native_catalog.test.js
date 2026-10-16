const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const search=require('../web 7M/miniprogram/features/catalog-search');
assert.equal(search.yuanToCents('18.25'),1825);
assert.throws(()=>search.yuanToCents('1.005'));
assert.equal(search.searchQuery('books','数据结构',{min_price_yuan:'0',max_price_yuan:'18.25',edition:'unknown',delivery:'delivery'}), 'category=books&q=%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84&edition=unknown&delivery=delivery&min_price=0&max_price=1825');
assert(!search.searchQuery('electronics','',{edition:'第二版'}).includes('edition'));
const calls=[],storage={};
const app={globalData:{user:{id:4},sessionVersion:0,baseURL:'http://local'},
 async request(path,data){calls.push({path,data});if(path==='/config')return {buildings:['C1']};
 if(path.startsWith('/product/edit?id='))return {id:9,version:3,fields:{title:'二手键盘',category:'electronics',price:'18.25'},photos:[]};
 if(path==='/product/edit')return {id:9};throw new Error('Unexpected '+path);}};
const wx={getStorageSync:k=>storage[k],setStorageSync:(k,v)=>{storage[k]=v;},removeStorageSync:k=>{delete storage[k];},showToast(){},redirectTo(){}};
function feature(name){const module={exports:{}};vm.runInNewContext(fs.readFileSync('web 7M/miniprogram/features/'+name+'.js','utf8'),{module,getApp:()=>app,wx,Promise,Error,Number,Object,JSON,String});return module.exports;}

let dialog;
wx.showModal=options=>{dialog=options;};
const actions=feature('catalog-actions');
actions.listAction.call({load(){},error(){throw new Error('should not run');}}, {currentTarget:{dataset:{id:9,action:'delist'}}});
app.globalData.sessionVersion++;
const before=calls.length;
dialog.success({confirm:true});assert.equal(calls.length,before,'old native confirmation must not borrow new session');
app.globalData.sessionVersion--;

let definition;
vm.runInNewContext(fs.readFileSync('web 7M/miniprogram/pages/publish/index.js','utf8'),{getApp:()=>app,Page:x=>{definition=x;},require:()=>feature('editing'),wx,setTimeout,clearTimeout,Math,Date,JSON,Promise,Set,Error,Number,Object,String});
const page={...definition,data:JSON.parse(JSON.stringify(definition.data)),setData(patch){Object.assign(this.data,patch);}};
(async()=>{
 await page.onLoad({edit:'9'});assert.equal(page.data.editingId,9);assert.equal(page.data.version,3);assert.equal(page.data.fields.price,'18.25');
 page.input({currentTarget:{dataset:{field:'price'}},detail:{value:'21.50'}});
 await page.persist();assert(!calls.some(x=>x.path==='/draft'),'editing must not publish a duplicate listing');
 assert.equal(storage['zj-native-edit-4-9'].fields.price,'21.50');
 await page.submit();const post=calls.find(x=>x.path==='/product/edit');assert.equal(post.data.version,3);assert.equal(post.data.fields.price,'21.50');
 clearTimeout(page._timer);
 console.log('Native catalog money/query contracts and versioned local edit workflow passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
