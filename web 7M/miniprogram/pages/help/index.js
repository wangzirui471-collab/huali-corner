const app=getApp();
const {shanghai}=require('../../utils');
const types=[['parcel','快递代取'],['documents','资料代交'],['moving','搬运帮忙'],['study','学习辅导／笔记整理'],['other','其他互助']];
Page({
 data:{items:[],typeNames:types.map(item=>item[1]),category:0,kind:0,date:'',clock:'18:00',writing:false,mine:false,cursor:null},
 onLoad(options){this.postId=options.id||'';this.setData({date:new Date(Date.now()+86400000).toISOString().slice(0,10)});},
 onShow(){this.load();},
 error(error){wx.showToast({title:error.message||'操作失败',icon:'none'});},
 identity(){const user=app.globalData.user?.id,epoch=app.globalData.sessionVersion;return ()=>user===app.globalData.user?.id&&epoch===app.globalData.sessionVersion;},
 async load(more=false){
  const current=this.identity();
  try{
   const query=this.postId?'post_id='+Number(this.postId)+'&status=all':this.data.mine?'mine=1&status=all':'';
   const result=await app.request('/help/posts?'+query+(more&&this.data.cursor?'&before_id='+this.data.cursor:''));
   if(!current())return;
   const rows=result.items.map(item=>({...item,rewardText:item.reward===null?'报酬面议':item.reward===0?'无偿互助':'意向报酬 ¥'+(item.reward/100).toFixed(2),deadlineText:shanghai(item.deadline),statusText:{open:'招募中',closed:'已关闭',expired:'已过期'}[item.status]}));
   this.setData({items:more?this.data.items.concat(rows):rows,cursor:result.next_cursor,hasMore:result.has_more,user:app.globalData.user});
  }catch(error){this.error(error);}
 },
 more(){this.load(true);},
 mine(){this.postId='';this.setData({mine:!this.data.mine});this.load();},
 publish(){if(!app.globalData.user){wx.navigateTo({url:'/pages/hub/index?tab=me'});return;}this.key=Date.now()+'-'+Math.random();this.setData({writing:true});},
 pickType(event){this.setData({category:Number(event.detail.value)});},
 pickKind(event){this.setData({kind:Number(event.detail.value)});},
 pickDate(event){this.setData({date:event.detail.value});},
 pickTime(event){this.setData({clock:event.detail.value});},
 cancel(){this.setData({writing:false});},
 async submit(event){
  if(this._submitting)return;this._submitting=true;const current=this.identity();
  try{
   await app.request('/help/posts',{...event.detail.value,kind:this.data.kind?'offer':'need',service_type:types[this.data.category][0],
    deadline:new Date(this.data.date+'T'+this.data.clock+':00+08:00').getTime()/1000,key:this.key});
   if(current()){this.postId='';this.setData({writing:false,mine:true});await this.load();}
  }catch(error){if(current())this.error(error);}finally{this._submitting=false;}
 },
 async contact(event){
  if(!app.globalData.user){wx.navigateTo({url:'/pages/hub/index?tab=me'});return;}
  const current=this.identity();
  try{const room=await app.request('/rooms/private',{peer:Number(event.currentTarget.dataset.user)});if(current())wx.navigateTo({url:'/pages/hub/index?tab=messages&room='+room.id});}catch(error){this.error(error);}
 },
 async status(event){const current=this.identity();try{await app.request('/help/status',{post_id:Number(event.currentTarget.dataset.id),status:event.currentTarget.dataset.status});if(current())this.load();}catch(error){this.error(error);}},
 feedback(event){
  if(!app.globalData.user){wx.navigateTo({url:'/pages/hub/index?tab=me'});return;}
  const current=this.identity(),postId=Number(event.currentTarget.dataset.id),type=event.currentTarget.dataset.type;
  wx.showModal({title:type==='report'?'举报互助信息':'客服反馈',editable:true,placeholderText:'请填写可核查的情况',success:async result=>{
   if(!result.confirm||!current())return;
   try{await app.request('/tickets',{type,post_id:postId,subject:'校园互助 #'+postId+' 反馈',body:result.content});if(current())wx.showToast({title:'已提交客服'});}catch(error){if(current())this.error(error);}
  }});
 }
});
