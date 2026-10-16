const app=getApp();
async function loadEditing(page,id,defaults){
 page._cacheKey='zj-native-edit-'+page._owner+'-'+id;
 const dto=await app.request('/product/edit?id='+Number(id));if(!page.current())return;
 const cached=wx.getStorageSync(page._cacheKey),local=cached?.dirty?cached:null;
 const photos=local?.photos||dto.photos,uploaded={},extraPhotos=[];
 for(const p of photos){if(p.angle==='extra')extraPhotos.push(p);else uploaded[p.angle]=p;}
 page.setData({editingId:Number(id),fields:{...defaults,...(local?.fields||dto.fields)},version:local?.version||dto.version,
 uploaded,extraPhotos,conflict:!!local && local.version!==dto.version,saveStatus:'修改仅保存本机；点击保存商品修改后提交'});
 page._dirty=!!local;page._lastSaved=local?'':JSON.stringify(page.snapshot());page.restorePhotos(page._stamp);
}
module.exports={loadEditing};
