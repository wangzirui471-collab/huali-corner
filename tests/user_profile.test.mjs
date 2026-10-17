// U03 contract source for A to run. No execution is performed by B.
import assert from 'node:assert/strict';

globalThis.window = {HUALI_STATIC_DEMO:false};
globalThis.sessionStorage = {getItem:()=>null};
globalThis.location = {hash:'#me'};

const {state} = await import('../web 7M/src/core/state.js');
const {userAvatar, publicAvatarURL} = await import('../web 7M/src/components/user-avatar.js');
const {userProfileForm, userProfileSummary, userAvatarForm, userProfileComparison}
  = await import('../web 7M/src/components/user-profile.js');
const {clicks, submits, isUserProfileConflict, avatarImageError}
  = await import('../web 7M/src/actions/user-profile.js');

const user = {id:101,nickname:'甲同学',college:'计算机工程学院',major:'软件工程',bio:'简介',
  degree_level:'junior_college',study_status:'graduated',education:'已毕业',
  profile_version:3,score:100,role:'user',avatar_url:null,avatar_upload_id:null};

for (const url of ['https://example.com/a.png','//evil.test/a','javascript:alert(1)',
                   '/media/../secret','data:image/svg+xml,x','/media/ua_'+ 'a'.repeat(32)+'?token=bad']) {
  assert.equal(publicAvatarURL(url),'','untrusted avatar URLs must not become images');
}
assert.equal(publicAvatarURL('/media/ua_'+'a'.repeat(32)), '/media/ua_'+'a'.repeat(32));
assert.ok(userAvatar({nickname:''}).includes('同学'),'empty nicknames need an accessible fallback');
assert.ok(!userAvatar({nickname:'<svg/onload=alert(1)>',avatar_url:'javascript:alert(1)'}).includes('<svg'));
assert.ok(userAvatar({nickname:'😀同学'}).includes('😀'),'fallback must preserve a full Unicode character');

const formHTML = userProfileForm(user);
assert.match(formHTML,/id="user-profile-form"/);
assert.ok(!formHTML.includes('id="profile-form"'));
assert.match(formHTML,/value="junior_college" selected/);
assert.match(formHTML,/value="graduated" selected/);
assert.match(formHTML,/maxlength="80"/);
assert.match(formHTML,/maxlength="300"/);
assert.ok(!formHTML.includes('name="college"'),'read-only college must not enter the new POST');
assert.ok(!userProfileForm({...user,bio:'</textarea><script>bad()</script>'}).includes('<script>'));
assert.match(userAvatarForm(user),/id="user-avatar-form"/);
assert.match(userProfileSummary({...user,major:'',bio:''}),/暂未填写/);
assert.match(userProfileSummary({nickname:'旧用户',education:'已毕业',score:100}),/已毕业/);
assert.match(userProfileComparison({...user,bio:'<img onerror=bad()>',profile_version:4}),/&lt;img/);
for (const key of [...Object.keys(clicks),...Object.keys(submits)]) {
  assert.ok(key.startsWith('user-'),'B must not overwrite existing action keys');
}
assert.equal(isUserProfileConflict({status:409}),true);
assert.equal(isUserProfileConflict(new Error('资料已更新，请重新载入并核对')),true);
assert.equal(isUserProfileConflict(new Error('网络失败')),false);

function fakeRoot() {
  const feedback = {textContent:'',innerHTML:'',dataset:{},focus(){}};
  const comparison = {innerHTML:'',hidden:true,dataset:{}};
  const summary = {innerHTML:''};
  const version = {value:'3'};
  const controls = [{disabled:false},{disabled:false}];
  const root = {isConnected:true,dataset:{userOwner:'101'},
    querySelector(selector) {
      return {'[data-user-profile-feedback]':feedback,'[data-user-avatar-feedback]':feedback,
        '[data-user-comparison]':comparison,'[data-user-summary]':summary}[selector] || null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-user-control]') return controls;
      if (selector === '[name="profile_version"]') return [version];
      return [];
    }};
  const fields = {profile_version:version,nickname:{value:'未保存昵称'},major:{value:'专业'},
    bio:{value:'保留我的输入'},degree_level:{value:'junior_college'},study_status:{value:'graduated'}};
  const form = {isConnected:true,elements:{namedItem:name=>fields[name]},
    closest:()=>root};
  return {root,form,feedback,version,fields,controls,comparison};
}

globalThis.document = {querySelector:()=>null,querySelectorAll:()=>[]};
state.me = {...user}; state.token = 'session-A'; state.renderId = 1;
const first = fakeRoot();
let release, started;
const entered = new Promise(resolve=>{started=resolve;});
let posts = 0;
globalThis.fetch = async (url,options) => {
  posts++;
  const payload = JSON.parse(options.body);
  assert.deepEqual(Object.keys(payload).sort(),
    ['bio','degree_level','major','nickname','profile_version','study_status']);
  started();
  return new Promise(resolve=>{release=resolve;});
};
const job = submits['user-profile-form']({form:first.form});
await entered;
await submits['user-profile-form']({form:first.form});
assert.equal(posts,1,'duplicate submissions must not send a second request');
state.me = {...user,id:102,nickname:'乙同学'}; state.token = 'session-B';
release({ok:true,status:200,json:async()=>({...user,nickname:'旧会话保存结果',profile_version:4})});
await job;
assert.equal(state.me.id,102,'late responses must not replace the new account');
assert.equal(first.fields.bio.value,'保留我的输入');

state.me = {...user}; state.token = 'session-A'; state.renderId = 1;
const conflicting = fakeRoot();
globalThis.fetch = async()=>({ok:false,status:409,json:async()=>({error:'资料已更新，请重新载入并核对'})});
await submits['user-profile-form']({form:conflicting.form});
assert.equal(conflicting.fields.bio.value,'保留我的输入');
assert.equal(conflicting.version.value,'3','409 must not automatically adopt a newer version');
assert.match(conflicting.feedback.innerHTML,/user-profile-compare/);
assert.equal(state.me.profile_version,3);

const failing = fakeRoot();
globalThis.fetch = async()=>{throw new Error('网络断开');};
await submits['user-profile-form']({form:failing.form});
assert.equal(failing.fields.bio.value,'保留我的输入');
assert.match(failing.feedback.textContent,/网络断开/);
assert.ok(failing.controls.every(control=>!control.disabled),'failure must restore controls');

const wrapper = {dataset:{userAvatarLabel:'甲同学的默认头像'},setAttribute(name,value){this[name]=value;}};
const broken = {hidden:false,matches:selector=>selector==='[data-user-avatar-image]',closest:()=>wrapper};
avatarImageError({target:broken});
assert.equal(broken.hidden,true);
assert.equal(wrapper['aria-label'],'甲同学的默认头像');
console.log('User center component, submission, conflict and late-session contract checks completed.');
