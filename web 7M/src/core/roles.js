'use strict';
// 权限层 · 角色层级判断
//
// 与后端 app/account/service.py 的 ROLE_RANK 一一对应：
//   user(0) < support(1) < admin(2) < developer(3)
//
// 为什么要有这个文件：以前各页面各写各的 `['support','admin'].includes(...)`，
// 开发者（developer）被漏在所有客服入口之外——后台接口明明允许，界面却
// 不显示「客服工作台」，工单页也不渲染「处理工单」表单，登录开发者账号
// 等于拿着一把没孔的钥匙。角色判断只在这里写一次，页面不要手写数组。

export const ROLE_RANK = { user: 0, support: 1, admin: 2, developer: 3 };

const rank = user => (user && ROLE_RANK[user.role]) || 0;

/** 客服及以上：能看工单队列、用户档案、内部备注。 */
export const isStaff = user => rank(user) >= 1;

/** 管理员及以上：能封号、调信誉、处置商品、任命客服。 */
export const isAdmin = user => rank(user) >= 2;

/** 是否开发者：最高权限，可任命管理员。 */
export const isDeveloper = user => rank(user) >= 3;
