const assert=require('node:assert/strict');
const {orderView}=require('../miniprogram/utils');
const result=orderView({buyer_id:1,seller:'卖家同学',buyer:'买家同学',total:1700,appointment:0,delivery:'delivery',address:'A2楼下',items:[{region:'A1楼下'}],status:'paid'},2);
assert.equal(result.location,'A2楼下');assert.equal(result.appointmentText,'1970-01-01 08:00');assert.equal(result.counterparty,'买家同学');assert.equal(result.deliveryText,'卖家送货');
assert.equal(orderView({buyer_id:1,seller:'卖家',buyer:'买家',total:0,appointment:0,delivery:'pickup',address:'',items:[{region:'A1楼下'}]},1).location,'A1楼下');
console.log('Native seller delivery instructions passed');
