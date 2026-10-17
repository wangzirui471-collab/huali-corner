'use strict';

import { e } from '../core/dom.js';

export function publicAvatarURL(value){
  return typeof value === 'string' && /^\/media\/ua_[0-9a-f]{32}$/.test(value) ? value : '';
}

export function userAvatar(user={}, size='large'){
  const name = typeof user.nickname === 'string' && user.nickname.trim() ? user.nickname.trim() : '同学';
  const initial = [...name][0];
  const url = publicAvatarURL(user.avatar_url);
  const safeSize = ['small','large'].includes(size) ? size : 'large';
  const label = name+'的默认头像';
  return `<span class="user-avatar user-avatar-${safeSize}" role="img" aria-label="${e(url ? name+'的头像' : label)}" data-user-avatar data-user-avatar-label="${e(label)}"><span class="user-avatar-fallback" aria-hidden="true">${e(initial)}</span>${url ? `<img data-user-avatar-image src="${e(url)}" alt="${e(name)}的头像" loading="lazy" decoding="async">` : ''}</span>`;
}
