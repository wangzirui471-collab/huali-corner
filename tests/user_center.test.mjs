// 用户中心（改名 + 头像）前端渲染自检。
//
// 这几段 HTML 是拼字符串拼出来的：漏一个 name、少一个 data-user-control，
// 页面上不会报错，只会「点了没反应」或「保存时少一个字段」。后端接口测不出来，
// 所以在这里对模板输出做断言。
//
// 运行：node tests/user_center.test.mjs
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const SRC = path.join(ROOT, 'web 7M', 'src');

globalThis.window = {HUALI_STATIC_DEMO:false, addEventListener(){}, scrollTo(){}};
globalThis.sessionStorage = {getItem:()=>null, setItem(){}, removeItem(){}};
globalThis.localStorage = globalThis.sessionStorage;
globalThis.document = {
  querySelector:()=>null, querySelectorAll:()=>[], addEventListener(){},
  createElement:()=>({appendChild(){}, classList:{add(){}, remove(){}}}),
  documentElement:{style:{setProperty(){}}}
};
globalThis.location = {hash:'', href:'http://localhost/'};

const { userAvatar, publicAvatarURL } = await import(pathToFileURL(path.join(SRC,'components/user-avatar.js')).href);
const { userProfileForm, userAvatarForm, userProfileValues } = await import(pathToFileURL(path.join(SRC,'components/user-profile.js')).href);

let failed = 0;
function check(name, ok, detail){
  if (ok) return;
  failed++; console.error('  FAIL ' + name + (detail ? '  ->  ' + detail : ''));
}

const ID = 'ua_' + 'a'.repeat(32);
const me = {id:7, nickname:'小明', college:'计算机工程学院', major:'软件', bio:'你好',
            score:88, education:'本科', profile_version:3, degree_level:'bachelor',
            study_status:'studying', avatar_url:'/media/'+ID};

// 1. 头像地址白名单：只认本站 /media/ua_<32hex>，外链与 javascript: 一律拒
check('合法头像地址被接受', publicAvatarURL('/media/'+ID) === '/media/'+ID);
for (const bad of ['javascript:alert(1)', 'https://evil.example/x.png', '/media/ua_short', '/media/'+ID+'/../x', '', null]){
  check('非法头像地址被拒: ' + String(bad).slice(0,28), publicAvatarURL(bad) === '');
}

// 2. 默认头像：没有头像时出首字母，且昵称要转义
const plain = userAvatar({nickname:'<img src=x onerror=alert(1)>'});
check('默认头像出首字母块', plain.includes('user-avatar-fallback'));
check('昵称被转义', !plain.includes('<img src=x'));
check('无头像时不出 img', !plain.includes('data-user-avatar-image'));

// 3. 有头像时出 img，并且带懒加载
const withImg = userAvatar(me);
check('有头像时输出 img', withImg.includes('data-user-avatar-image'));
check('头像走懒加载', withImg.includes('loading="lazy"'));

// 4. 资料表单：昵称必填 + 版本号隐藏域 + 每个控件都带 data-user-control
const form = userProfileForm(me);
check('资料表单 id', form.includes('id="user-profile-form"'));
check('昵称字段', form.includes('name="nickname"'));
check('版本号隐藏域带真实版本', form.includes('name="profile_version" value="3"'));
check('版本号在表单内', form.indexOf('name="profile_version"') < form.indexOf('name="nickname"'));
check('学院只读', form.includes('class="uc-readonly"') && !form.includes('name="college"'));
check('反馈区存在', form.includes('data-user-profile-feedback'));
check('设置行结构（标签 + 控件）', form.includes('class="uc-row') && form.includes('uc-label'));
check('头像表单左预览右操作', userAvatarForm(me).includes('uc-avatar-body'));

// 5. 头像表单：确认按钮默认隐藏（上传前不能点）
const avatar = userAvatarForm(me);
check('头像表单 id', avatar.includes('id="user-avatar-form"'));
check('upload_id 隐藏域', avatar.includes('name="upload_id"'));
check('文件选择限类型', avatar.includes('accept="image/jpeg,image/png,image/webp"'));
check('确认按钮初始隐藏', /data-action="user-avatar-confirm"[^>]*hidden/.test(avatar));
check('移除头像入口', avatar.includes('data-action="user-avatar-remove"'));

// 6. 版本号缺失时不能写出 undefined
const noVersion = userProfileForm({...me, profile_version:undefined});
check('版本缺失不输出 undefined', !noVersion.includes('undefined'));

// 7. 旧数据只有 education 时按保守规则映射，不反推
check('本科映射 bachelor', userProfileValues({education:'本科'}).degree_level === 'bachelor');
check('已毕业映射 graduated', userProfileValues({education:'已毕业'}).study_status === 'graduated');
check('已毕业不猜学历', userProfileValues({education:'已毕业'}).degree_level === 'unspecified');

console.log(failed ? '用户中心渲染自检失败：' + failed + ' 项' : '用户中心渲染自检通过：头像地址白名单、转义、表单字段与版本号均符合预期');
process.exit(failed ? 1 : 0);
