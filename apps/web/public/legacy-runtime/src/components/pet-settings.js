'use strict';
// 桌宠设置：换宠物 / 调大小 / 行为开关 / 用户须知。
//
// 布局照桌面端设置的习惯来：左侧分区导航、右侧一组一组的设置项，
// 每项「标题 + 一句说明 + 控件在右」。手机上导航折成顶部横向标签，
// 免得一个 300px 宽的弹窗里塞两根竖条。
//
// 这里只管界面和偏好读写；真正把皮肤贴到桌宠身上由 ai-pet.js 订阅
// onPetPrefChange 后自己做——设置面板不该知道桌宠怎么渲染。

import { $ } from '../core/dom.js';
import {
  SKINS, SKIN_LIST, PENDING_SKINS, DEFAULT_SKIN, currentSkin, customSkin,
  saveCustomSkin, clearCustomSkin, getSkinId, setSkinId,
  getScale, setScale, getLife, setLife, getHidden, setHidden,
  hasReadNotice, markNoticeRead, forgetPosition,
  pullPetPrefs, schedulePushPetPrefs, uploadCustomSkin,
} from './pet-skins.js';

const TABS = [
  ['pet', '桌宠'],
  ['look', '外观'],
  ['behave', '行为'],
  ['about', '须知'],
];

const listeners = [];
export function onPetPrefChange(fn){ if (typeof fn === 'function') listeners.push(fn); }
function emit(what){ listeners.forEach(fn => { try{ fn(what); }catch(_){ } }); }

function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// --- 用户须知 ---------------------------------------------------------
// 参照「京东京言用户使用须知」的骨架：服务内容 / 对象 / 用途 / 规范 /
// 知识产权 / 免责 / 其他。措辞按校园二手 + AI 助手的实际情况重写，
// 不直接照搬电商条款（比如「购物灵感」这种跟我们无关的部分一律删掉）。

const NOTICE = `
<p class="ps-lead">欢迎使用「转角」AI 助手桌宠。为了让你清楚它能做什么、不能做什么，请在使用前读完这份须知。</p>

<h4>一、这是什么</h4>
<p>桌宠是转角内置的 AI 助手，目前提供三项服务：</p>
<p>1. <b>平台问答</b>：发布、下单、付款、面交、退款、售后、好友、信誉、客服时间等规则问题，按平台现行规则回答。</p>
<p>2. <b>开放闲聊</b>：跟校园生活、二手行情、心情有关的话题都可以聊，它也会接话。</p>
<p>3. <b>发布助手</b>：帮你写商品描述、给出参考估价区间。</p>
<p>你可以随时换掉它的形象（小转 / 大乔 / 小毛 / 自己上传），换形象不影响它回答的内容。</p>

<h4>二、谁能用</h4>
<p>1. 本服务面向已注册的转角用户。注册即表示你具备使用本服务所需的行为能力。</p>
<p>2. 未满 18 周岁的用户，应在监护人知情并同意的前提下使用。</p>
<p>3. 账号因违规被封禁期间，本服务同时停止。</p>

<h4>三、回答的效力</h4>
<p>1. 桌宠的回答<b>仅供参考</b>，不构成平台承诺、合同条款或处理结论。金额、时限、处罚以页面显示和客服书面答复为准。</p>
<p>2. 涉及交易纠纷的定性、退款金额、信誉处罚，仍由客服依《转角社区规范》处理，AI 无权代替判断。</p>
<p>3. AI 可能出错，包括记错规则、编造细节。发现它说错了，请以「帮助与客服」页面的说明为准，并把情况反馈给我们。</p>

<h4>四、你不能用它做什么</h4>
<p>1. 不得要求它生成违法违规、侵害他人权益、违背公序良俗的内容。</p>
<p>2. 不得借它实施欺诈、刷单、恶意举报、骚扰他人、绕过平台风控等行为。</p>
<p>3. 不得把它的输出用于伪造平台通知、冒充客服或学校工作人员。</p>
<p>4. 不得用自动化手段批量调用接口，或试图获取系统提示、密钥、他人数据。</p>

<h4>五、你的输入与隐私</h4>
<p>1. 请不要输入密码、恢复码、完整手机号、身份证号、银行卡号等敏感信息。它不需要这些，也不该知道。</p>
<p>2. 为生成回答，你输入的内容会发送给第三方 AI 服务（当前为 DeepSeek）。对话内容不会作为公开内容展示。</p>
<p>3. 若部署为本地模型模式，问题不会离开本机，面板底部会注明。</p>
<p>4. 提问次数有每日上限，用于控制成本；上限在设置页可以看到。</p>

<h4>六、自定义形象</h4>
<p>1. 上传的图片<b>仅保存在你自己的浏览器</b>，不上传服务器，也不对其他用户可见。</p>
<p>2. 你应确保对该图片拥有使用权，不得上传他人肖像、涉密或违法内容。</p>
<p>3. 换设备、清缓存后自定义形象会丢失，需要重新上传。</p>

<h4>七、其他</h4>
<p>1. 本服务可能因模型故障、网络、额度耗尽而暂时不可用，此时可以直接说「转人工」或提交工单。</p>
<p>2. 我们会按需更新本须知，更新后在设置页重新打开即可看到。继续使用即视为接受更新后的内容。</p>
<p>3. 本须知未尽事项，适用《转角用户协议》与《转角隐私政策》。</p>
`;

// --- 设置弹窗 ---------------------------------------------------------

let root = null;
let activeTab = 'pet';

function skinCards(){
  const cur = getSkinId();
  const custom = customSkin();
  const cards = SKIN_LIST.map(s => `
    <button type="button" class="ps-skin${s.id === cur ? ' is-on' : ''}" data-skin="${s.id}" role="radio" aria-checked="${s.id === cur}">
      <span class="ps-skin-pic"><img src="${esc(s.avatar)}" alt="" loading="lazy"></span>
      <span class="ps-skin-txt"><b>${esc(s.name)}</b><small>${esc(s.note || '')}</small></span>
      <span class="ps-tick" aria-hidden="true">✓</span>
    </button>`);
  // 形象还没画好的角色占个位子，别让它点出个没反应的空按钮。
  PENDING_SKINS.forEach(p => {
    cards.push(`
    <button type="button" class="ps-skin is-pending" disabled aria-disabled="true">
      <span class="ps-skin-pic is-empty">?</span>
      <span class="ps-skin-txt"><b>${esc(p.name)}</b><small>${esc(p.note || '')}</small></span>
    </button>`);
  });
  cards.push(`
    <button type="button" class="ps-skin${cur === 'custom' ? ' is-on' : ''}" data-skin="custom" role="radio" aria-checked="${cur === 'custom'}">
      <span class="ps-skin-pic${custom ? '' : ' is-empty'}">${custom ? `<img src="${esc(custom.atlas)}" alt="">` : '＋'}</span>
      <span class="ps-skin-txt"><b>${custom ? esc(custom.name) : '自定义'}</b><small>${custom ? '点右侧可重新上传' : '上传一张图片当桌宠'}</small></span>
      <span class="ps-tick" aria-hidden="true">✓</span>
    </button>`);
  return cards.join('');
}

function panelHtml(){
  const scale = getScale();
  return `
  <section class="ps-pane" data-pane="pet"${activeTab === 'pet' ? '' : ' hidden'}>
    <header class="ps-head"><h3>桌宠</h3><p>换一只陪你待在角角落落里的小家伙。换形象不影响它回答的内容。</p></header>
    <div class="ps-card">
      <div class="ps-skins" role="radiogroup" aria-label="选择桌宠">${skinCards()}</div>
    </div>
    <div class="ps-card">
      <label class="ps-row ps-row-file">
        <span class="ps-row-txt"><b>上传自己的图</b><small>建议方形、主体居中、背景简单的图。会压缩后存在这台设备上。</small></span>
        <span class="ps-ctl"><span class="btn secondary ps-upload">选择图片</span></span>
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" id="ps-file" hidden>
      </label>
      ${customSkin() ? `
      <div class="ps-row">
        <span class="ps-row-txt"><b>删除自定义形象</b><small>删除后回到默认桌宠，已上传的图不会上传到服务器。</small></span>
        <span class="ps-ctl"><button type="button" class="btn secondary" data-ps="del-custom">删除</button></span>
      </div>` : ''}
    </div>
  </section>

  <section class="ps-pane" data-pane="look"${activeTab === 'look' ? '' : ' hidden'}>
    <header class="ps-head"><h3>外观</h3><p>调整它在页面上的存在感。</p></header>
    <div class="ps-card">
      <div class="ps-row">
        <span class="ps-row-txt"><b>大小</b><small><span id="ps-scale-val">${Math.round(scale * 100)}</span>%　往右拖会更大，小一点不挡内容。</small></span>
        <span class="ps-ctl"><input type="range" min="60" max="160" step="5" value="${Math.round(scale * 100)}" id="ps-scale" aria-label="桌宠大小"></span>
      </div>
      <div class="ps-row">
        <span class="ps-row-txt"><b>显示桌宠</b><small>关掉之后，随时可以从「我的 → 桌宠设置」重新打开。</small></span>
        <span class="ps-ctl"><label class="ps-switch"><input type="checkbox" id="ps-show"${getHidden() ? '' : ' checked'}><i></i></label></span>
      </div>
      <div class="ps-row">
        <span class="ps-row-txt"><b>重置位置</b><small>拖乱之后点一下，回到右下角。</small></span>
        <span class="ps-ctl"><button type="button" class="btn secondary" data-ps="reset-pos">复位</button></span>
      </div>
    </div>
  </section>

  <section class="ps-pane" data-pane="behave"${activeTab === 'behave' ? '' : ' hidden'}>
    <header class="ps-head"><h3>行为</h3><p>不想它太活泼的时候，可以安静一点。</p></header>
    <div class="ps-card">
      <div class="ps-row">
        <span class="ps-row-txt"><b>自动小动作</b><small>待机时偶尔挥挥手、跳一下。关掉后只有你操作它才动。</small></span>
        <span class="ps-ctl"><label class="ps-switch"><input type="checkbox" id="ps-life"${getLife() ? ' checked' : ''}><i></i></label></span>
      </div>
      <div class="ps-row">
        <span class="ps-row-txt"><b>拖动后记住位置</b><small>位置存在这台设备上，换设备不跟随。</small></span>
        <span class="ps-ctl"><span class="ps-hint">已开启</span></span>
      </div>
    </div>
  </section>

  <section class="ps-pane" data-pane="about"${activeTab === 'about' ? '' : ' hidden'}>
    <header class="ps-head"><h3>须知</h3><p>关于它能做什么、不能做什么，以及你的图片存在哪里。</p></header>
    <div class="ps-card">
      <div class="ps-row">
        <span class="ps-row-txt"><b>用户使用须知</b><small>建议首次使用前读一遍，约 2 分钟。</small></span>
        <span class="ps-ctl"><button type="button" class="btn secondary" data-ps="notice">查看</button></span>
      </div>
      <div class="ps-row">
        <span class="ps-row-txt"><b>AI 说明</b><small>回答由第三方模型生成，仅供参考；金额、时限以页面为准。</small></span>
        <span class="ps-ctl"><span class="ps-hint">${hasReadNotice() ? '已读' : '未读'}</span></span>
      </div>
    </div>
  </section>`;
}

export function openPetSettings(tab){
  if (tab) activeTab = tab;
  if (!root){
    const el = document.createElement('div');
    el.className = 'ps-layer';
    el.innerHTML = `
      <div class="ps-backdrop" data-ps="close"></div>
      <div class="ps-sheet" role="dialog" aria-modal="true" aria-label="桌宠设置">
        <aside class="ps-nav" aria-label="设置分区">
          <header>桌宠设置</header>
          ${TABS.map(([k, label]) => `<button type="button" data-tab="${k}"${k === activeTab ? ' class="active"' : ''}>${label}</button>`).join('')}
        </aside>
        <div class="ps-body">
          <button type="button" class="ps-x" data-ps="close" aria-label="关闭">×</button>
          <div class="ps-panes">${panelHtml()}</div>
        </div>
      </div>`;
    document.body.appendChild(el);
    root = el;
    bind();
  }
  root.hidden = false;
  renderPanes();
  return root;
}

export function closePetSettings(){
  if (root) root.hidden = true;
}

function renderPanes(){
  if (!root) return;
  const box = root.querySelector('.ps-panes');
  if (box) box.innerHTML = panelHtml();
  root.querySelectorAll('.ps-nav button').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === activeTab);
  });
  bindPanes();
}

function bind(){
  root.addEventListener('click', ev => {
    const tab = ev.target.closest('[data-tab]');
    if (tab){ activeTab = tab.dataset.tab; renderPanes(); return; }
    const act = ev.target.closest('[data-ps]');
    if (!act) return;
    const kind = act.dataset.ps;
    if (kind === 'close'){ closePetSettings(); return; }
    if (kind === 'notice'){ openPetNotice(); return; }
    if (kind === 'reset-pos'){
      forgetPosition();
      emit('position');
      return;
    }
    if (kind === 'del-custom'){
      clearCustomSkin();
      schedulePushPetPrefs(0);
      renderPanes();
      emit('skin');
      return;
    }
  });
  bindPanes();
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape') return;
    const layer = $('.pn-layer');
    if (layer && !layer.hidden){ closePetNotice(); return; }
    if (root && !root.hidden) closePetSettings();
  });
}

function bindPanes(){
  if (!root) return;

  root.querySelectorAll('[data-skin]').forEach(btn => {
    btn.onclick = () => {
      const id = btn.dataset.skin;
      if (id === 'custom' && !customSkin()){
        root.querySelector('#ps-file')?.click();
        return;
      }
      setSkinId(id);
      schedulePushPetPrefs();
      renderPanes();
      emit('skin');
    };
  });

  const file = root.querySelector('#ps-file');
  if (file) file.onchange = () => handleUpload(file);

  const scale = root.querySelector('#ps-scale');
  if (scale){
    scale.oninput = () => {
      const v = Number(scale.value) / 100;
      setScale(v);
      schedulePushPetPrefs();
      const label = root.querySelector('#ps-scale-val');
      if (label) label.textContent = String(Math.round(v * 100));
      emit('scale');
    };
  }

  const show = root.querySelector('#ps-show');
  if (show){
    show.onchange = () => {
      setHidden(!show.checked);
      schedulePushPetPrefs();
      emit('show');
    };
  }

  const life = root.querySelector('#ps-life');
  if (life){
    life.onchange = () => {
      setLife(life.checked);
      schedulePushPetPrefs();
      emit('life');
    };
  }
}

// --- 上传 -------------------------------------------------------------
// 压到长边 480：桌宠显示高度约 100px，再大纯属浪费；也避开 localStorage 5MB 上限。

function handleUpload(input){
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  if (!/^image\//.test(file.type)){ toast('请选择图片文件'); return; }
  if (file.size > 8 * 1024 * 1024){ toast('图片太大了，请选 8MB 以内'); return; }

  const reader = new FileReader();
  reader.onerror = () => toast('读不了这张图，换一张试试');
  reader.onload = () => {
    const img = new Image();
    img.onerror = () => toast('这张图解码失败，换一张试试');
    img.onload = () => {
      try{
        const max = 480;
        const k = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * k));
        const h = Math.max(1, Math.round(img.height * k));
        const cv = document.createElement('canvas');
        cv.width = w; cv.height = h;
        const ctx = cv.getContext('2d');
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(img, 0, 0, w, h);
        let url = '';
        try{ url = cv.toDataURL('image/webp', .92); }catch(_){ url = ''; }
        if (!url || url.indexOf('data:image/webp') !== 0) url = cv.toDataURL('image/png');
        if (url.length > 3.6 * 1024 * 1024){
          toast('图片压不小，换一张简单点的（或裁小一点）');
          return;
        }
        // 不用文件名当展示名：手机相册导出的是 IMG_20261023_161234 这种，
        // 截断后更难看。统一叫「我的桌宠」。
        saveCustomSkin(url, w, h, '我的桌宠');
        renderPanes();
        markNoticeRead();
        emit('skin');
        toast('已换成你上传的桌宠');
        // 传上去之后换设备也能用；失败就只留本机，不打扰用户
        uploadCustomSkin(url);
      }catch(_){
        toast('图片处理失败，换一张试试');
      }
    };
    img.src = String(reader.result || '');
  };
  reader.readAsDataURL(file);
}

// --- 用户须知 ---------------------------------------------------------

let noticeEl = null;

export function openPetNotice(){
  if (!noticeEl){
    noticeEl = document.createElement('div');
    noticeEl.className = 'pn-layer';
    noticeEl.innerHTML = `
      <div class="pn-backdrop" data-pn="close"></div>
      <div class="pn-sheet" role="dialog" aria-modal="true" aria-label="用户使用须知">
        <header class="pn-head">
          <div><b>转角 AI 助手用户使用须知</b><small>版本 2026-10 · 适用于桌宠与客服问答</small></div>
          <button type="button" class="pn-x" data-pn="close" aria-label="关闭">×</button>
        </header>
        <div class="pn-body">${NOTICE}</div>
        <footer class="pn-foot">
          <small>继续使用即视为已阅读并同意本须知。</small>
          <button type="button" class="btn primary" data-pn="agree">我知道了</button>
        </footer>
      </div>`;
    document.body.appendChild(noticeEl);
    noticeEl.addEventListener('click', ev => {
      if (ev.target.closest('[data-pn]')) {
        const k = ev.target.closest('[data-pn]').dataset.pn;
        if (k === 'agree') markNoticeRead();
        closePetNotice();
      }
    });
  }
  noticeEl.hidden = false;
  const body = noticeEl.querySelector('.pn-body');
  if (body) body.scrollTop = 0;
  return noticeEl;
}

export function closePetNotice(){
  if (noticeEl) noticeEl.hidden = true;
}

function toast(msg){
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('show'), 2200);
}
