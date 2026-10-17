'use strict';
// 页面层 · 取货清单（同卖家合并取货）
import { $, e } from '../core/dom.js';
import { money } from '../core/format.js';
import { state, saveCart } from '../core/state.js';
import { api } from '../core/http.js';
import { shell, heading, empty } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { needLogin } from '../auth/login.js';

export async function cartPage(){if(!needLogin())return;const products=await Promise.all(state.cart.map(id=>api('/product?id='+id).catch(()=>null)));state.cart=products.filter(Boolean).map(p=>p.id);saveCart();const ps=products.filter(Boolean);shell(`${heading('PICKUP TOGETHER','取货清单','同一卖家多件合并取货，书籍仍逐本计价。')}<div class="cart-layout"><section class="panel">${ps.map(p=>`<div class="cart-item"><img src="${e(p.photos[0].url)}" alt="${e(p.title)}"><div><h3>${e(p.title)}</h3><p>${e(p.nickname)} · ${e(p.region)}</p><b>¥${money(p.price)}</b></div><button class="text-button" data-action="remove-cart" data-id="${p.id}">移除</button></div>`).join('')||empty('清单还是空的')}</section>${ps.length?`<form id="checkout-form" class="panel checkout-panel"><h2>约定交付</h2>${state.pendingWant?`<div class="notice">本次结算关联求购 #${state.pendingWant.want}，成交将记 5% 撮合服务费（模拟）。<button class="text-button" data-action="clear-want">取消关联</button></div>`:''}${selectField('交付方式','delivery',[['pickup','自提，不收送货费'],['delivery','卖家送货，合并收一次']])}${field('送货地址（公共收货点）','address','text','','placeholder="如 A2楼下入口，自提无需填写"')}${field('约定日期和时间','appointment','datetime-local','','required')}<div class="order-summary"><p>商品合计 <b>¥${money(ps.reduce((s,p)=>s+p.price,0))}</b></p><p>送货费 <b id="delivery-total">¥0</b></p><p class="sum">合计 <b id="checkout-total">¥${money(ps.reduce((s,p)=>s+p.price,0))}</b></p></div><small>已接受的还价以订单内最终价格为准；只支持同卖家合并。试用无真实付款。</small><button class="btn primary full" type="submit">生成模拟订单</button></form>`:''}</div>`,'orders');$('#checkout-form')?.addEventListener('change',()=>{const isDelivery=$('[name=delivery]').value==='delivery';const fee=isDelivery?Math.max(...ps.map(p=>p.delivery_fee)):0;$('#delivery-total').textContent='¥'+money(fee);$('#checkout-total').textContent='¥'+money(fee+ps.reduce((s,p)=>s+p.price,0));});}
