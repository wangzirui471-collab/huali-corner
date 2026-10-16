const app=getApp();
const {demoCover}=require('../../utils');
const {searchQuery}=require('../../features/catalog-search');
Page({
 data:{products:[],category:'',q:'',filters:{},showFilters:false,hasMore:false,
  deliveryOptions:['不限','自提','送货（含送货费）'],sortOptions:['最新发布','价格从低到高','价格从高到低']},
 onLoad(options={}){if(options.filters)try{this.setData(JSON.parse(decodeURIComponent(options.filters)));}catch{}},
 onShow(){this._noticeUnsubscribe?.();this._noticeUnsubscribe=app.watchNotifications?.(count=>this.setData({notificationCount:count}));app.startNotifications?.();this.load();},
 onHide(){this._noticeUnsubscribe?.();},
 onUnload(){this._noticeUnsubscribe?.();this._generation=(this._generation||0)+1;},
 async load(more=false){
  const generation=this._generation=(this._generation||0)+1,epoch=app.globalData.sessionVersion;
  try{
   const query=searchQuery(this.data.category,this.data.q,this.data.filters,more?this._cursor:null);
   const result=await app.request('/products/search?'+query);
   if(generation!==this._generation||epoch!==app.globalData.sessionVersion)return;
   const items=result.items.map(x=>({...x,cover:app.absolute(x.photos[0].url),coverStyle:demoCover(x,app.globalData.baseURL),isPhoto:!x.photos[0].url.endsWith('.svg'),priceText:(x.price/100).toFixed(2),delivered:((x.price+x.delivery_fee)/100).toFixed(2)}));
   const products=more?[...this.data.products]:[],seen=new Set(products.map(x=>x.id));
   for(const item of items)if(!seen.has(item.id)){products.push(item);seen.add(item.id);}
   this._cursor=result.next_cursor;this.setData({products,hasMore:result.has_more});
  }catch(e){if(generation===this._generation)wx.showToast({title:e.message,icon:'none'});}
 },
 more(){if(this.data.hasMore)this.load(true);},
 search(e){this.setData({q:e.detail.value.q});this.load();},
 category(e){this.setData({category:e.currentTarget.dataset.id});this.load();},
 toggleFilters(){this.setData({showFilters:!this.data.showFilters});},
 filterInput(e){this.setData({filters:{...this.data.filters,[e.currentTarget.dataset.field]:e.detail.value}});},
 chooseFilter(e){const k=e.currentTarget.dataset.field;this.setData({filters:{...this.data.filters,[k]:(k==='delivery'?['','pickup','delivery']:['','price','price_desc'])[Number(e.detail.value)]}});},
 applyFilters(){try{searchQuery(this.data.category,this.data.q,this.data.filters);this.setData({showFilters:false});this.load();}catch(e){wx.showToast({title:e.message,icon:'none'});}},
 clearFilters(){this.setData({filters:{},q:'',category:'',showFilters:false});this.load();},
 detail(e){wx.navigateTo({url:'/pages/detail/index?id='+e.currentTarget.dataset.id});},
 nav(e){const t=e.currentTarget.dataset.tab;if(t==='publish')wx.navigateTo({url:'/pages/publish/index'});else wx.navigateTo({url:'/pages/hub/index?tab='+t});},
 onShareAppMessage(){return {title:'转角 · 校园二手好物',path:'/pages/home/index?filters='+encodeURIComponent(JSON.stringify({category:this.data.category,q:this.data.q,filters:this.data.filters}))};}
});
