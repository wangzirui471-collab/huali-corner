// Parse yuan without floating point rounding or silently accepting extra precision.
export function yuanToCents(value){
 const text=String(value).trim();
 if(!/^\d+(\.\d{1,2})?$/.test(text))throw new Error('价格请输入最多两位小数的非负金额');
 const [whole,fraction='']=text.split('.');
 const cents=Number(whole)*100+Number(fraction.padEnd(2,'0'));
 if(!Number.isSafeInteger(cents)||cents>1000000)throw new Error('价格须在0至10000元之间');
 return cents;
}
