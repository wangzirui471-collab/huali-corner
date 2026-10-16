// Private draft/delisted media is fetched with the captured owner's credentials.
import { state } from './state.js';
export function releaseMedia(){for(const url of state.mediaURLs)URL.revokeObjectURL(url);state.mediaURLs.clear();}
export async function listingMedia(product){
 if(product.status!=='removed'||product.seller_id!==state.me?.id)return product;
 const token=state.token,epoch=state.renderId;
 const photos=await Promise.all(product.photos.map(async photo=>{
  if(!photo.url.startsWith('/media/'))return photo;
  const response=await fetch(photo.url,{headers:{Authorization:'Bearer '+token}});
  if(!response.ok)throw new Error('商品图片读取失败，请刷新后重试');
  const blob=await response.blob();
  if(token!==state.token||epoch!==state.renderId)throw new Error('页面或账号已切换');
  const url=URL.createObjectURL(blob);state.mediaURLs.add(url);return {...photo,url};
 }));
 return {...product,photos};
}
