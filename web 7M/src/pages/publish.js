'use strict';
// 页面层 · 发布闲置（单页五段式 + 实时预览）
//
// F-04：第 04 步「分类参数」按所选分类显示——书籍字段（版次/出版社/
//   笔记/缺页…）只在二手书分类出现，电子/运动/生活各有自己的字段。
//   旧实现把书籍字段无条件渲染给所有分类。
//
// F-02：发布草稿存 localStorage（按账号隔离、500ms 防抖），刷新或离开
//   后重新进入发布页可恢复；照片是 File 对象无法持久化，恢复后需重新
//   选择。跨设备草稿需要服务端 drafts 表，属后续阶段，此处不涉及。
import { $, icon, toast } from '../core/dom.js';
import { state } from '../core/state.js';
import { shell, heading, modal, closeModal } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { card } from '../components/product-card.js';
import { needLogin } from '../auth/login.js';
import { loadDraft, saveDraft, clearDraft, makeDraftSaver } from '../core/drafts.js';

export async function publish(){if(!needLogin())return;const buildings=state.config.buildings||[];
const cats=[['books','二手书','教材与课外书','book'],['living','宿舍生活','桌椅台灯收纳','home'],['sports','运动闲置','球拍与装备','ball'],['electronics','电子产品','耳机键盘数码','device']];
// F-04：每个分类只暴露自己的字段，共用的「成色 / 购买时间」留在第 03 步。
const CAT_FIELDS={
  books:()=>({title:'二手书信息',hint:'仅二手书必填，一本一条以免混淆版本',html:
    selectField('版次','edition',['版本待确认','第一版','第二版','第三版','第七版','第八版','其他版本，见介绍'])
    +field('出版社','publisher','text','','placeholder="不确定可填待确认"')
    +field('作者／编者（可选）','author')
    +field('ISBN（可选）','isbn')
    +selectField('笔记情况','notes',['无笔记','少量笔记','大量笔记','未核对，交付时检查'])
    +selectField('缺页情况','missing',['无缺页','有缺页，见介绍','未核对，交付时检查'])
    +selectField('附件情况','accessories',['无附件','附件齐全','附件缺失，见介绍','未核对，交付时检查'])
    +field('适用专业／课程（可选）','course')}),
  electronics:()=>({title:'数码参数',hint:'品牌型号写清楚，方便买家比对',html:
    field('品牌','brand','text','','placeholder="如：索尼、罗技、小米"')
    +field('型号','model','text','','placeholder="如：WH-1000XM5、Keychron K3"')
    +selectField('保修情况','warranty',['无保修','保修期内','保修待核对'])
    +selectField('配件情况','accessories',['无附件','配件齐全','附件缺失，见介绍','未核对，交付时检查'])}),
  sports:()=>({title:'装备信息',hint:'尺码规格写清楚，减少来回询问',html:
    field('品牌','brand','text','','placeholder="如：尤尼克斯、李宁"')
    +field('尺码／规格','size','text','','placeholder="如：球拍 4U G5、泳镜大号"')
    +selectField('使用频次','frequency',['偶尔使用','每周数次','高频使用，功能正常','待核对'])}),
  living:()=>({title:'物品信息',hint:'材质尺寸写清楚，自提时好认',html:
    field('材质','material','text','','placeholder="如：实木、不锈钢、塑料"')
    +field('尺寸','size','text','','placeholder="如：桌面 80×40cm"')
    +selectField('使用频次','frequency',['偶尔使用','每周数次','高频使用，功能正常','待核对'])}),
};
const previewSeed={id:0,title:'你的标题会出现在这里',category:'books',price:0,delivery_fee:0,delivery:'pickup',region:'公共交付区域',status:'available',photos:[{url:'/assets/item0.svg'}],nickname:state.me.nickname,seller_id:state.me.id,simulation:false,favorited:false,condition:'正常使用痕迹'};
shell(`${heading('A NEW CHAPTER','给闲置一个新去处','一次填一项，不用一次就想完美。发布后可以随时下架。')}<div class="publish-layout"><form id="publish-form" class="publish-form"><section class="panel publish-step"><div class="step-head"><span class="step-number">01</span><div><h2>这是什么</h2><p>先选分类，再写清楚它的情况</p></div></div><div class="cat-picker">${cats.map(([v,t,s,ic])=>`<label class="cat-option"><input type="radio" name="category" value="${v}"${v==='books'?' checked':''}><span class="cat-ico">${icon(ic)}</span><b>${t}</b><small>${s}</small></label>`).join('')}</div><label class="field"><span>商品标题 *</span><input name="title" type="text" required maxlength="80" placeholder="如：数据结构 第二版，有少量笔记"></label><label class="field"><span>商品介绍 *</span><textarea name="description" required maxlength="3000" placeholder="使用情况、缺陷，以及想告诉下一个主人的话…"></textarea></label></section><section class="panel publish-step"><div class="step-head"><span class="step-number">02</span><div><h2>实拍三张</h2><p>正面、侧面、顶部各一张，重复图片不计数</p></div></div><div class="photo-inputs">${[['front','正面','封面 / 主视图'],['side','侧面','书脊 / 侧边'],['top','顶部','书页顶 / 底部']].map(([a,t,h])=>`<label class="upload-slot"><span>${icon('camera')}</span><b>${t} *</b><small>${h}</small><input type="file" name="${a}" accept="image/jpeg,image/png,image/webp" required><div class="upload-preview"></div></label>`).join('')}</div><label class="field"><span>内页 / 缺陷补图（可选，最多 6 张）</span><input type="file" name="extra" multiple accept="image/jpeg,image/png,image/webp"><small>不强制额外拍摄；未提供时买家可在交付时检查。单张不超过 5MB。</small></label></section><section class="panel publish-step"><div class="step-head"><span class="step-number">03</span><div><h2>价格与成色</h2><p>定价由你判断，填 0 表示免费送</p></div></div><div class="form-grid"><label class="field"><span>售价（元）*</span><div class="input-affix"><i>¥</i><input name="price" type="number" required min="0" max="10000" step="0.01" placeholder="0"></div></label><label class="field"><span>原购买价（可不填）</span><div class="input-affix"><i>¥</i><input name="original_price" type="number" min="0" max="10000" step="0.01" placeholder="填了会显示折扣"></div></label>${field('购买时间（可不填）','bought','month')}${selectField('成色','condition',['正常使用痕迹','近乎全新','明显磨损，已说明'])}</div></section><section class="panel publish-step"><div class="step-head"><span class="step-number">04</span><div><h2 id="cat-fields-title">二手书信息</h2><p id="cat-fields-hint">仅二手书必填，一本一条以免混淆版本</p></div></div><div class="form-grid" id="cat-fields-grid">${CAT_FIELDS.books().html}</div></section><section class="panel publish-step"><div class="step-head"><span class="step-number">05</span><div><h2>在哪里交接</h2><p>只写校园公共区域，不要写宿舍门牌</p></div></div><div class="form-grid">${selectField('交付方式','delivery',[['both','自提 / 卖家送货均可'],['pickup','仅自提'],['delivery','仅卖家送货']])}${selectField('公共交付区域','building',buildings)}<label class="field"><span>送货费（元）</span><div class="input-affix"><i>¥</i><input name="delivery_fee" type="number" value="2" min="0" max="10000" step="0.01"></div></label>${field('公共碰面点说明','point','text','楼下入口','required maxlength="40"')}</div><p class="muted">同卖家多件合并交付只收一次送货费，按其中最高的一件计算。订单内价格固定，不支持订单外补款。</p></section><div class="submit-row sticky-submit"><span>当前信誉 <b>${state.me.score}/100</b> · 低于 60 分暂停发布</span><button class="btn primary lg" type="submit">确认发布 ${icon('arrow')}</button></div></form><aside class="publish-preview"><div class="preview-inner"><span class="eyebrow">LIVE PREVIEW</span><h3>别人的第一眼</h3><div id="publish-preview">${card(previewSeed)}</div><ul class="preview-tips"><li>${icon('check')}标题写清版次与成色，比只写书名好卖</li><li>${icon('check')}三张实拍比一段长描述更有说服力</li><li>${icon('check')}发布后可以随时下架、改价或重新上架</li></ul></aside></div>`,'publish');

 // F-04：切换分类时重渲染第 04 步字段，并同步预览。
 const renderCatFields=cat=>{const cfg=(CAT_FIELDS[cat]||CAT_FIELDS.books)();$('#cat-fields-title').textContent=cfg.title;$('#cat-fields-hint').textContent=cfg.hint;$('#cat-fields-grid').innerHTML=cfg.html;};
 const form=$('#publish-form');
 const syncPreview=()=>{const box=$('#publish-preview');if(!box)return;const fd=new FormData(form);const seed={...previewSeed,title:fd.get('title')||previewSeed.title,category:fd.get('category')||'books',price:Math.round(Number(fd.get('price')||0)*100),original_price:Math.round(Number(fd.get('original_price')||0)*100),delivery:fd.get('delivery')||'pickup',delivery_fee:Math.round(Number(fd.get('delivery_fee')||0)*100),condition:fd.get('condition')||previewSeed.condition,edition:fd.get('edition')||'',region:(fd.get('building')||'')+' · '+(fd.get('point')||'')};box.innerHTML=card(seed);};

 // F-02：草稿的读写。文字字段全量快照，照片不进草稿（恢复时需重选）。
 const DRAFT_FIELDS=['title','description','category','price','original_price','bought','condition','edition','publisher','author','isbn','notes','missing','accessories','course','brand','model','warranty','size','material','frequency','delivery','building','delivery_fee','point'];
 const collectDraft=()=>{const fd=new FormData(form);const o={};for(const k of DRAFT_FIELDS)o[k]=String(fd.get(k)||'');return o;};
 const saveSoon=makeDraftSaver(state.me.id);
 const applyDraft=v=>{
   renderCatFields(v.category||'books');        // 先把草稿分类的字段渲染出来，再回填值
   for(const k of DRAFT_FIELDS){
     if(k==='category'){const r=form.elements.category;if(r)for(const el of(r.length?r:[r]))el.checked=(el.value===(v.category||'books'));}
     else{const el=form.elements[k];if(el&&el.type!=='radio')el.value=v[k]||'';}
   }
   syncPreview();
 };
 const saved=loadDraft(state.me.id);
 if(saved){
   modal(`<h2>恢复未发布完的内容？</h2><p class="muted">你上次填到一半离开了（保存于 ${new Date(saved.savedAt).toLocaleString('zh-CN',{hour12:false})}）。恢复后三张照片需要重新选择。</p><div class="modal-actions"><button class="btn primary" id="draft-restore">恢复草稿</button><button class="btn secondary" id="draft-discard">丢弃</button></div>`);
   $('#draft-restore').onclick=()=>{applyDraft(saved.values);closeModal();toast('已恢复上次草稿，照片请重新选择');};
   $('#draft-discard').onclick=()=>{clearDraft(state.me.id);closeModal();};
 }
 form?.addEventListener('input',()=>{syncPreview();saveSoon(collectDraft());});
 form?.addEventListener('change',ev=>{if(ev.target.name==='category'){renderCatFields(ev.target.value);syncPreview();saveSoon(collectDraft());}});
}
