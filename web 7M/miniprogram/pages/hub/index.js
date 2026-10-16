const app=getApp();const {orderView}=require('../../utils');const labels={awaiting_payment:'待付款',paid:'待交付',awaiting_handover:'待核对交接',awaiting_receipt:'待确认收货',completed:'已完成',cancelled:'已取消',disputed:'售后中',refunded:'已退款',open:'待处理',resolved:'已解决',processing:'处理中',review:'待复核'};
Page({...require('../../features/catalog-actions'),data:{tab:'me',authMode:'password',authView:'login',user:null,rooms:[],messages:[],orders:[],tickets:[],posts:[],cart:[],date:'',clock:'18:00',delivery:'pickup',code:'',currentRoom:0},onLoad(o){this.options=o;this.setData({tab:o.tab==='listings'?'selling':o.tab||'me',currentRoom:Number(o.room)||0,date:new Date(Date.now()+86400000).toISOString().slice(0,10)});},onShow(){if(this.data.user&&this.data.user.id!==app.globalData.user?.id)this.clearPrivate();this.setData({user:app.globalData.user});this._noticeUnsubscribe?.();this._noticeUnsubscribe=app.watchNotifications?.(count=>this.setData({notificationCount:count}));app.startNotifications?.();this.load();},onHide(){clearInterval(this.timer);this._noticeUnsubscribe?.();},onUnload(){clearInterval(this.timer);this._noticeUnsubscribe?.();},error(e){wx.showToast({title:e.message||'操作失败',icon:'none',duration:3000});},authView(e){this.setData({authView:e.currentTarget.dataset.mode});},async load(){try{const config=await app.request('/config');this.setData({authMode:config.auth_mode||'demo',buildingChoices:['自由填写',...(config.buildings||[])]});const t=this.data.tab;if(t==='profile'){const r=await app.request('/profile?id='+this.options.user);this.setData({profile:r.user,products:r.products.map(p=>({...p,priceText:(p.price/100).toFixed(2)}))});return;}if(t==='community'){this.setData({posts:await app.request('/posts')});return;}if(!app.globalData.user)return;if(t==='me'){const user=await app.request('/me');app.globalData.user=user;this.setData({user});}if(t==='orders'){const orders=await app.request('/orders');this.setData({orders:orders.map(o=>({...orderView(o,app.globalData.user.id),statusText:labels[o.status]}))});}if(t==='support'||t==='staff'){const tickets=await app.request('/tickets');this.setData({tickets:tickets.map(x=>({...x,statusText:labels[x.status]}))});}if(t==='selling'){const products=await app.request('/seller/products');this.setData({selling:products.map(p=>({...p,priceText:(p.price/100).toFixed(2)}))});}if(t==='credit'){const creditHistory=await app.request('/credit/history');const creditRules=await app.request('/credit/rules');this.setData({creditHistory,creditRules});}if(t==='favorites'){const p=await app.request('/products?favorite=1');this.setData({products:p.map(x=>({...x,priceText:(x.price/100).toFixed(2)}))});}if(t==='messages'){await this.loadNotices();const r=await app.request('/rooms');this.setData({rooms:r.joined});if(this.data.currentRoom){clearInterval(this.timer);await this.loadMessages();this.timer=setInterval(()=>this.loadMessages(),4000);}}if(t==='cart'){const ids=wx.getStorageSync('hc-cart-'+app.globalData.user.id)||[];const ps=await Promise.all(ids.map(id=>app.request('/product?id='+id)));this.setData({cart:ps.map(p=>({...p,priceText:(p.price/100).toFixed(2)}))});}}catch(e){this.error(e);}},nav(e){clearInterval(this.timer);this.setData({tab:e.currentTarget.dataset.tab,currentRoom:0});this.load();},async demo(e){if(this.data.authMode==='password'){this.error(new Error('试用版已关闭演示账号'));return;}try{this.clearPrivate();await app.demoLogin(e.currentTarget.dataset.phone);this.setData({user:app.globalData.user});await this.load();}catch(x){this.error(x);}},async code(e){this.phone=e.detail.value;},async sendCode(){try{const r=await app.request('/auth/code',{phone:this.phone});this.setData({code:r.demo_code});}catch(e){this.error(e);}},async login(e){try{const values=e.detail.value,isRegistration=this.data.authMode==='password'&&this.data.authView==='register';if(isRegistration){if(values.password!==values.password_confirm)throw new Error('两次密码不一致');if(!values.agree||!values.agree.includes('yes'))throw new Error('请先确认试用说明');}this.clearPrivate();const r=await app.request(isRegistration?'/auth/register':'/auth/login',values);app.globalData.sessionVersion=(app.globalData.sessionVersion||0)+1;wx.setStorageSync('hc-token',r.token);wx.setStorageSync('hc-user',r.user);app.globalData.user=r.user;this.setData({user:r.user});app.startNotifications?.();await this.load();if(r.recovery_code)wx.showModal({title:'请私下保存账号恢复码',content:r.recovery_code+'\n仅本次显示。勿发群聊。密码找回或修改请使用试用网站。',showCancel:false});}catch(x){this.error(x);}},clearPrivate(){app.stopNotifications?.();app.globalData.sessionVersion=(app.globalData.sessionVersion||0)+1;clearInterval(this.timer);this.cursor=0;this.setData({user:null,orders:[],tickets:[],activeTicket:null,activeTicketOrder:null,canHandleTicket:false,selling:[],creditHistory:[],creditRules:[],rooms:[],messages:[],cart:[],products:[],currentRoom:0,messageText:'',notices:[],noticeCursor:0,noticeMore:false,notificationCount:0,checkoutAddress:'',rescheduleId:null,rescheduleAddress:''});},logout(){if(app.globalData.user)wx.removeStorageSync('zj-native-draft-'+app.globalData.user.id);app.request('/auth/logout',{}).catch(()=>{});this.clearPrivate();app.globalData.sessionVersion=(app.globalData.sessionVersion||0)+1;wx.removeStorageSync('hc-token');wx.removeStorageSync('hc-user');app.globalData.user=null;this.setData({user:null});},async saveProfile(e){try{const u=await app.request('/me',{...e.detail.value,education:this.data.user.education});app.globalData.user=u;wx.setStorageSync('hc-user',u);this.setData({user:u});wx.showToast({title:'资料已保存'});}catch(x){this.error(x);}},async join(e){if(!this.data.user){this.setData({tab:'me'});return;}try{const r=await app.request('/rooms/join',{kind:e.currentTarget.dataset.kind});this.setData({tab:'messages',currentRoom:r.id});this.load();}catch(x){this.error(x);}},selectRoom(e){this.cursor=0;this.setData({currentRoom:e.currentTarget.dataset.id,messages:[]});this.load();},async loadMessages(){try{const room=this.data.currentRoom;const r=await app.request('/messages?room_id='+room+'&after='+(this.cursor||0));if(room!==this.data.currentRoom)return;const existing=new Set(this.data.messages.map(m=>m.id));const fresh=r.filter(m=>!existing.has(m.id));this.setData({messages:this.data.messages.concat(fresh)});if(r.length)this.cursor=r[r.length-1].id;}catch(e){clearInterval(this.timer);this.error(e);}},async message(e){try{await app.request('/messages',{room_id:this.data.currentRoom,body:e.detail.value.body,key:Date.now()+'-'+Math.random()});this.setData({messageText:''});this.loadMessages();}catch(x){this.error(x);}},async post(e){if(!this.data.user){this.setData({tab:'me'});return;}try{await app.request('/posts',{body:e.detail.value.body,topic:'交流'});this.setData({postText:''});this.load();}catch(x){this.error(x);}},detail(e){wx.navigateTo({url:'/pages/detail/index?id='+e.currentTarget.dataset.id});},async checkout(e){try{const v=e.detail.value;const ids=this.data.cart.map(p=>p.id);await app.request('/checkout',{product_ids:ids,delivery:this.data.delivery,address:v.address || this.data.checkoutAddress,appointment:new Date(this.data.date+'T'+this.data.clock+':00+08:00').getTime()/1000,key:Date.now()+'-'+Math.random()});wx.setStorageSync('hc-cart-'+this.data.user.id,[]);this.setData({tab:'orders'});this.load();}catch(x){this.error(x);}},date(e){this.setData({date:e.detail.value});},clock(e){this.setData({clock:e.detail.value});},delivery(e){this.setData({delivery:e.detail.value==='0'?'pickup':'delivery'});},async change(e){try{await app.request('/order/change',{id:e.currentTarget.dataset.id,accept:e.currentTarget.dataset.accept==='yes'});this.load();}catch(x){this.error(x);}},propose(e){const order=this.data.orders.find(item=>item.id===Number(e.currentTarget.dataset.id));if(!order)return;const local=new Date(order.appointment*1000+8*3600000).toISOString();this.setData({rescheduleId:order.id,rescheduleDate:local.slice(0,10),rescheduleClock:local.slice(11,16),rescheduleAddress:order.location});},async orderAction(e){const id=e.currentTarget.dataset.id,action=e.currentTarget.dataset.action;wx.showModal({title:'确认订单操作',content:action==='receive'?'请先检查实物，确认后模拟结算。':'仅模拟订单，不扣真实款项。',success:async r=>{if(r.confirm)try{await app.request('/order/action',{id,action});this.load();}catch(x){this.error(x);}}});},  // Capture identity before opening dialogs or uploading evidence.
  identity() {
    const owner = app.globalData.user?.id, epoch = app.globalData.sessionVersion;
    return () => !!owner && app.globalData.user?.id === owner && app.globalData.sessionVersion === epoch;
  },
  drafts() { wx.navigateTo({ url: '/pages/publish/index?drafts=1' }); },
  async relist(event) {
    const current = this.identity();
    try {
      const draft = await app.request('/relist', { product_id: Number(event.currentTarget.dataset.id) });
      if (current()) wx.navigateTo({ url: '/pages/publish/index?id=' + draft.id });
    } catch (error) { this.error(error); }
  },
  ticket(event) {
    const orderId = Number(event.currentTarget.dataset.id) || null;
    const type = event.currentTarget.dataset.type || (orderId ? 'refund' : 'other');
    const current = this.identity();
    const prompt = (refundMode = 'refund_only') => wx.showModal({
      title: orderId ? '说明售后问题' : type === 'appeal' ? '提交信誉申诉' : '向客服反馈',
      editable: true, placeholderText: '说明事实、关联订单或处罚记录编号',
      success: async result => {
        if (!result.confirm || !result.content || !current()) return;
        try {
          await app.request('/tickets', { type, order_id: orderId, refund_mode: refundMode,
            subject: orderId ? '订单售后' : type === 'appeal' ? '信誉申诉' : '用户反馈', body: result.content });
          if (current()) { this.setData({ tab: 'support' }); await this.load(); }
        } catch (error) { this.error(error); }
      },
    });
    if (orderId) wx.showActionSheet({ itemList: ['仅退款（不恢复库存）', '退货退款（需确认收到实物）'],
      success: choice => { if (current()) prompt(choice.tapIndex === 1 ? 'return_refund' : 'refund_only'); } });
    else prompt();
  },
  async openTicket(event) {
    const current = this.identity();
    try {
      const ticket = await app.request('/ticket?id=' + Number(event.currentTarget.dataset.id));
      if (!current()) return;
      const order = ticket.order_id ? await app.request('/order?id=' + ticket.order_id) : null;
      if (!current()) return;
      const user = app.globalData.user;
      const participant = ticket.user_id === user.id || order && [order.buyer_id, order.seller_id].includes(user.id);
      this.setData({ activeTicket: ticket, activeTicketOrder: order,
        canHandleTicket: ['admin', 'support'].includes(user.role) && !participant,
        refundAmount: order ? ((ticket.requested_amount || order.total) / 100).toFixed(2) : '' });
    } catch (error) { this.error(error); }
  },
  async replyTicket(event) {
    const id = this.data.activeTicket.id, current = this.identity();
    try {
      await app.request('/ticket/reply', { id, body: event.detail.value.body });
      if (current()) await this.openTicket({ currentTarget: { dataset: { id } } });
    } catch (error) { this.error(error); }
  },
  returnAction(event) {
    const id = this.data.activeTicket.id, action = event.currentTarget.dataset.action, current = this.identity();
    wx.showModal({ title: '确认实物退回', content: '只有实际完成交接后才能确认。退款仍需管理员审核。',
      success: async result => {
        if (!result.confirm || !current()) return;
        try {
          await app.request('/ticket/return', { id, action });
          if (current()) await this.openTicket({ currentTarget: { dataset: { id } } });
        } catch (error) { this.error(error); }
      },
    });
  },
  amountInput(event) { this.setData({ refundAmount: event.detail.value }); },
  resolve(event) {
    const outcome = event.currentTarget.dataset.action, id = this.data.activeTicket.id;
    const current = this.identity(), amount = this.data.refundAmount;
    wx.showModal({ title: '填写处理依据', editable: true, placeholderText: '核实事实、双方意见及理由',
      success: async result => {
        if (!result.confirm || !result.content || !current()) return;
        try {
          await app.request('/ticket/resolve', { id, outcome, reason: result.content,
            ...(['refund', 'request_refund'].includes(outcome) ? { amount_yuan: amount } : {}) });
          if (current()) { await this.load(); await this.openTicket({ currentTarget: { dataset: { id } } }); }
        } catch (error) { this.error(error); }
      },
    });
  },
  addEvidence() {
    const id = this.data.activeTicket.id, current = this.identity();
    wx.chooseMedia({ count: 6, mediaType: ['image'], success: async result => {
      try {
        const evidence = [];
        for (const file of result.tempFiles) {
          if (!current()) return;
          if (file.size > 5 * 1024 * 1024) throw new Error('每张图片最多5MB');
          const content = await new Promise((resolve, reject) => wx.getFileSystemManager().readFile({
            filePath: file.tempFilePath, encoding: 'base64', success: value => resolve(value.data), fail: reject,
          }));
          if (!current()) return;
          const upload = await app.request('/upload', { content, angle: 'proof', private: true });
          evidence.push(upload.id);
        }
        if (!current()) return;
        await app.request('/ticket/reply', { id, body: '补充图片证据', evidence });
        if (current()) await this.openTicket({ currentTarget: { dataset: { id } } });
      } catch (error) { this.error(error); }
    } });
  },
  evidence(event) {
    const current = this.identity(), id = event.currentTarget.dataset.id;
    wx.downloadFile({ url: app.globalData.baseURL + '/media/' + encodeURIComponent(id),
      header: { Authorization: 'Bearer ' + (wx.getStorageSync('hc-token') || '') },
      success: response => {
        if (!current()) return;
        if (response.statusCode !== 200) { this.error(new Error('不能读取证据，客服请先认领')); return; }
        wx.previewImage({ urls: [response.tempFilePath] });
      }, fail: () => this.error(new Error('证据读取失败，请重试')),
    });
  },
  async loadNotices(before = 0) {
    const current = this.identity();
    const result = await app.request('/notifications' + (before ? '?before=' + before : ''));
    if (!current()) return;
    const notices = before ? this.data.notices.concat(result.items) : result.items;
    this.setData({notices,noticeCursor:before?this.data.noticeCursor:result.latest_id,
      noticeMore:result.has_more,notificationCount:result.unread_count});
  },
  async refreshNotices() { try { await this.loadNotices(); await app.refreshNotifications?.(); } catch(error) { this.error(error); } },
  async moreNotices() { try { await this.loadNotices(this.data.notices[this.data.notices.length-1].id); } catch(error) { this.error(error); } },
  async readNotices() {
    if (!this.data.noticeCursor) return;
    const current = this.identity();
    try {
      await app.request('/notifications/read',{through_id:this.data.noticeCursor});
      if (current()) await this.refreshNotices();
    } catch(error) { this.error(error); }
  },
  async openNotice(event) {
    const current = this.identity(), id = Number(event.currentTarget.dataset.id);
    const notice = this.data.notices.find(item=>item.id===id);
    if (!notice) return;
    try {
      await app.request('/notifications/read',{id});
      if (!current()) return;
      await app.refreshNotifications?.();
      if (!current()) return;
      if (notice.entity_type==='ticket') {
        this.setData({tab:'support'});await this.load();
        if (current()) await this.openTicket({currentTarget:{dataset:{id:notice.entity_id}}});
      } else {
        this.setData({tab:'orders',focusOrderId:notice.entity_id});await this.load();
        if (current()) wx.pageScrollTo?.({selector:'#order-'+notice.entity_id});
      }
    } catch(error) { this.error(error); }
  },
  subscriptionInfo() {
    wx.showModal({title:'微信系统提醒尚未接入',content:'当前可用的是小程序内未读提示。微信订阅消息还需要真实AppID、获批模板，并接入服务端发送接口及配置，单独申请权限不会收到提醒。小程序关闭后不保证通知。',showCancel:false});
  },
  checkoutBuilding(event) {
    const building=this.data.buildingChoices[Number(event.detail.value)];
    if (building && building!=='自由填写') this.setData({checkoutAddress:building+'楼下公共入口'});
  },
  addressInput(event) { this.setData({checkoutAddress:event.detail.value}); },
  rescheduleBuilding(event) {
    const building=this.data.buildingChoices[Number(event.detail.value)];
    if(building && building!=='自由填写')this.setData({rescheduleAddress:building+'楼下公共入口'});
  },
  rescheduleAddressInput(event) { this.setData({rescheduleAddress:event.detail.value}); },
  rescheduleDateInput(event) { this.setData({rescheduleDate:event.detail.value}); },
  rescheduleClockInput(event) { this.setData({rescheduleClock:event.detail.value}); },
  cancelReschedule() { this.setData({rescheduleId:null,rescheduleAddress:''}); },
  async rescheduleSubmit() {
    const current=this.identity();
    try {
      await app.request('/order/action',{id:this.data.rescheduleId,action:'reschedule',
        address:this.data.rescheduleAddress,
        appointment:new Date(this.data.rescheduleDate+'T'+this.data.rescheduleClock+':00+08:00').getTime()/1000});
      if(current()){this.cancelReschedule();await this.load();}
    }catch(error){this.error(error);}
  },
});
