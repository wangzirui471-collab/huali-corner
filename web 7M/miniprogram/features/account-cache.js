module.exports={
 clearDeviceCopies(userId){
  if(!userId)return;
  const keys=wx.getStorageInfoSync?.().keys||[];
  for(const key of keys)if(key==='zj-native-draft-'+userId||key.startsWith('zj-native-edit-'+userId+'-'))wx.removeStorageSync(key);
  wx.removeStorageSync('zj-native-draft-'+userId);wx.removeStorageSync('hc-cart-'+userId);
 }
};
