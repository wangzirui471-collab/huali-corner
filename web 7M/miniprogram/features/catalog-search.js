function yuanToCents(value){
 const text=String(value).trim();if(!/^\d+(\.\d{1,2})?$/.test(text))throw new Error('金额最多两位小数');
 const [whole,fraction='']=text.split('.'),cents=Number(whole)*100+Number(fraction.padEnd(2,'0'));
 if(!Number.isSafeInteger(cents)||cents>1000000)throw new Error('金额须在0至10000元之间');return cents;
}
function searchQuery(category,q,filters,cursor){
 const f={category,q};
 for(const k of ['college','major','course','edition','condition','delivery','sort'])if(filters[k])f[k]=filters[k];
 if(category && category!=='books')for(const k of ['major','course','edition'])delete f[k];
 for(const k of ['min_price','max_price'])if(String(filters[k+'_yuan']||'').trim())f[k]=yuanToCents(filters[k+'_yuan']);
 if(f.min_price!=null&&f.max_price!=null&&f.min_price>f.max_price)throw new Error('最低价不能高于最高价');
 if(cursor)f.cursor=cursor;
 return Object.keys(f).filter(k=>f[k]!==undefined&&f[k]!=='').map(k=>encodeURIComponent(k)+'='+encodeURIComponent(f[k])).join('&');
}
module.exports={searchQuery,yuanToCents};
