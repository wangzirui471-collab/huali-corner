import { state } from '../core/state.js';

export async function showEvidence(context, button) {
  const group=button.closest('.case-evidence-buttons,.case-source-photos')||button.parentElement;
  const ids=[...group.querySelectorAll('[data-operation="evidence"]')].map(b=>b.dataset.id);
  if(!ids.length)ids.push(button.dataset.id);
  const photos=await Promise.all(ids.map(async id=>{
    const response=await fetch('/media/'+encodeURIComponent(id),{headers:{Authorization:'Bearer '+context.session}});
    if(!response.ok)throw new Error('不能读取图片，请检查工单认领状态和账号权限');
    return {id,blob:await response.blob()};
  }));
  if(!context.isCurrent())return;
  for(const photo of photos){photo.url=URL.createObjectURL(photo.blob);state.mediaURLs.add(photo.url);}
  context.modal(`<h2>图片核查</h2><p class="muted">点击缩略图切换查看；仅按当前账号权限加载。</p><img class="evidence-view" alt="工单关联图片"><div class="evidence-gallery">${photos.map((photo,i)=>`<button type="button" aria-label="查看第${i+1}张图片"><img src="${photo.url}" alt="第${i+1}张缩略图"></button>`).join('')}</div>`);
  const viewer=document.querySelector('#overlay .evidence-view');
  viewer.src=photos.find(photo=>photo.id===button.dataset.id)?.url||photos[0].url;
  document.querySelectorAll('#overlay .evidence-gallery button').forEach((item,i)=>{item.onclick=()=>{viewer.src=photos[i].url;};});
}
