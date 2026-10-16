// Owner and session are captured before any native confirmation dialog opens.
const app=getApp();
const capture=()=>{
 const owner=app.globalData.user?.id,epoch=app.globalData.sessionVersion;
 return ()=>owner===app.globalData.user?.id && epoch===app.globalData.sessionVersion;
};
module.exports={
 listAction(event){
  const id=Number(event.currentTarget.dataset.id),action=event.currentTarget.dataset.action,current=capture();
  wx.showModal({title:action==='delist'?'确认下架？':'确认恢复上架？',
   content:'仅主动下架的商品可直接恢复；售后和违规移除需先核对记录。',
   success:async result=>{if(!result.confirm||!current())return;
    try{await app.request('/product/status',{id,action});if(current())this.load();}catch(error){if(current())this.error(error);}}});
 },
 editOrder(event){
  const id=Number(event.currentTarget.dataset.id),order=this.data.orders.find(o=>o.id===id),current=capture();
  if(!order)return;
  if(!order.isBuyer){this.askTime(id,undefined,undefined,current);return;}
  wx.showActionSheet({itemList:['自提（不收送货费）','卖家送货'],success:result=>{
   if(!current())return;
   const delivery=result.tapIndex===0?'pickup':'delivery';
   if(delivery==='delivery')wx.showModal({title:'收货公共地点',editable:true,content:order.location||'',success:address=>{
    if(address.confirm&&current())this.askTime(id,delivery,address.content,current);
   }});else this.askTime(id,delivery,'',current);
  }});
 },
 askTime(id,delivery,address,current=capture()){
  wx.showModal({title:'新交付时间',editable:true,placeholderText:'YYYY-MM-DD HH:mm（北京时间）',success:async result=>{
   if(!result.confirm||!current())return;
   const appointment=new Date(result.content.replace(' ','T')+':00+08:00').getTime()/1000;
   try{
    if(!Number.isFinite(appointment))throw new Error('请按 YYYY-MM-DD HH:mm 填写时间');
    await app.request('/order/update',{id,appointment,...(delivery?{delivery,address}:{})});
    if(current()){wx.showToast({title:'订单已修改'});this.load();}
   }catch(error){if(current())this.error(error);}
  }});
 },
 editProduct(event){wx.navigateTo({url:'/pages/publish/index?edit='+event.currentTarget.dataset.id});}
};
