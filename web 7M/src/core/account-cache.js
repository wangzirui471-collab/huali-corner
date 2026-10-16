// Remove only the departing account's readable device copies; server drafts survive.
export function clearAccountCaches(userId){
  if(!userId)return;
  try{
    const keys=[];
    for(let i=0;i<localStorage.length;i++)keys.push(localStorage.key(i));
    for(const key of keys)if(key===`zj-draft-${userId}`||key?.startsWith(`zj-edit-${userId}-`))localStorage.removeItem(key);
    localStorage.removeItem(`zj-draft-${userId}`);
  }catch{/* Restricted storage is already unreadable; continue clearing the session. */}
  try{sessionStorage.removeItem('hc-cart-'+userId);}catch{}
}
