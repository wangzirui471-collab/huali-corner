const pad=n=>String(n).padStart(2,'0');
function shanghai(t){const d=new Date(t*1000+8*3600000);return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;}
function orderView(o,userId){return {...o,totalText:(o.total/100).toFixed(2),isBuyer:o.buyer_id===userId,appointmentText:shanghai(o.appointment),location:o.address||(o.items[0]&&o.items[0].region)||'待确认',deliveryText:o.delivery==='pickup'?'自提':'卖家送货',counterparty:o.buyer_id===userId?o.seller:o.buyer,changes:(o.changes||[]).map(c=>({...c,timeText:shanghai(c.appointment),canRespond:c.proposer!==userId&&c.status==='pending'}))};}
module.exports={orderView,shanghai};
