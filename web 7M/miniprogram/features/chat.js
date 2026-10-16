const app=getApp();
module.exports={
 async loadMessages(){
  if(this._chatBusy||this._chatVisible===false||this.data.tab!=='messages')return;
  this._chatBusy=true;
  const room=this.data.currentRoom,current=this.identity();
  try{
   const messages=await app.request('/messages?room_id='+room+'&after='+(this.cursor||0));
   if(!current()||room!==this.data.currentRoom||this._chatVisible===false||this.data.tab!=='messages')return;
   const ids=new Set(this.data.messages.map(item=>item.id));
   const fresh=messages.filter(item=>!ids.has(item.id));
   this.setData({messages:this.data.messages.concat(fresh)});
   if(messages.length)this.cursor=Math.max(this.cursor||0,messages[messages.length-1].id);
   if(this.cursor)await app.request('/messages/read',{room_id:Number(room),through_id:this.cursor});
   const rooms=await app.request('/rooms');
   if(current()&&room===this.data.currentRoom)this.setData({rooms:rooms.joined});
  }catch(error){if(current())this.error(error);}finally{this._chatBusy=false;}
 }
};
