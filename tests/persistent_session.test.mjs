import assert from 'node:assert/strict';
import test from 'node:test';
import {readSessionToken, rememberSession, forgetSession, subscribeSession} from '../web 7M/src/core/session.js';

function storage(){
  const data=new Map();
  return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)};
}
function setup(){
  globalThis.localStorage=storage();globalThis.sessionStorage=storage();
  const handlers={};globalThis.window={addEventListener:(name,fn)=>{handlers[name]=fn;}};
  return handlers;
}
test('login survives a fresh tab without storing credentials or the user profile',()=>{
  setup();rememberSession('opaque-token');sessionStorage=storage();
  assert.equal(readSessionToken(),'opaque-token');
  assert.equal(localStorage.getItem('hc-token'),'opaque-token');
  assert.equal(localStorage.getItem('password'),null);
});
test('remembered login expires after 30 days and reading does not renew it',()=>{
  setup();rememberSession('opaque-token');
  const expires=Number(localStorage.getItem('hc-token-expires'));
  assert.ok(Math.abs(expires-Date.now()-30*86400000)<1000);
  assert.equal(readSessionToken(expires-1),'opaque-token');
  assert.equal(Number(localStorage.getItem('hc-token-expires')),expires);
  assert.equal(readSessionToken(expires),'');
  assert.equal(localStorage.getItem('hc-token'),null);
});
test('existing tab sessions are migrated without requiring another password',()=>{
  setup();sessionStorage.setItem('hc-token','legacy-token');
  assert.equal(readSessionToken(),'legacy-token');sessionStorage=storage();
  assert.equal(readSessionToken(),'legacy-token');
});
test('invalid expiry metadata is rejected instead of keeping a token forever',()=>{
  for(const expires of ['0','not-a-date']){
    setup();localStorage.setItem('hc-token','token');localStorage.setItem('hc-token-expires',expires);
    assert.equal(readSessionToken(),'');
  }
});
test('logout removes both persistent and legacy session tokens',()=>{
  setup();rememberSession('token');sessionStorage.setItem('hc-token','old-token');
  forgetSession();assert.equal(readSessionToken(),'');
  assert.equal(localStorage.getItem('hc-token-expires'),null);
});
test('logout in another tab cannot revive this tab legacy token',()=>{
  const handlers=setup();rememberSession('token');sessionStorage.setItem('hc-token','old-token');
  let observed;subscribeSession(token=>{observed=token;});
  localStorage.removeItem('hc-token');handlers.storage({key:'hc-token'});
  assert.equal(observed,'');assert.equal(sessionStorage.getItem('hc-token'),null);
});
test('another tab switching account is observed, unrelated storage is ignored',()=>{
  const handlers=setup();rememberSession('first');let observed='unchanged';
  subscribeSession(token=>{observed=token;});handlers.storage({key:'cart'});
  assert.equal(observed,'unchanged');rememberSession('second');handlers.storage({key:'hc-token'});
  assert.equal(observed,'second');
});
test('blocked persistent storage falls back to the current browser session',()=>{
  setup();globalThis.localStorage={getItem(){throw Error('denied');},setItem(){throw Error('denied');},removeItem(){throw Error('denied');}};
  assert.doesNotThrow(()=>rememberSession('token'));
  const expires=String(Date.now()+10000);sessionStorage.setItem('hc-token-expires',expires);
  assert.equal(readSessionToken(),'token');
  assert.equal(sessionStorage.getItem('hc-token-expires'),expires);
  forgetSession();assert.equal(readSessionToken(),'');
});
