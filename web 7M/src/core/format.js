'use strict';
// 基础设施层 · 金额与时间格式化
// 后端所有金额以「分」为单位存储，前端展示时才除以 100。

export const money = n => (Number(n)/100).toFixed(n%100?2:0);

export const date = t => new Date(t*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});

// 把后端秒级时间戳转成 <input type="datetime-local"> 需要的本地字符串。
export function toLocalInput(ts){
  const d = new Date((ts||Date.now()/1000)*1000), p = n => String(n).padStart(2,'0');
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());
}
