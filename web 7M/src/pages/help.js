import { api } from '../core/http.js';
import { state } from '../core/state.js';
import { shell, heading, empty } from '../core/shell.js';
import { field, selectField } from '../components/forms.js';
import { helpTypes, helpCard } from '../components/help.js';

export async function helpPage(id,query){
 const filters=new URLSearchParams(query||'');
 if(id){filters.set('post_id',id);filters.set('status','all');}
 const result=await api('/help/posts?'+filters);
 const filterSelect=(label,name,options)=>{const value=filters.get(name)||'';return selectField(label,name,options).replace(`value="${value}"`,`value="${value}" selected`);};
 shell(`${heading('CAMPUS HELP','校园互助','快递代取、资料代交、搬运和学习互助，让零散需求找到愿意帮忙的人。')}<section class="panel"><div class="section-heading"><p>先发布，再私聊协商。平台不收取真实服务费，不托管服务报酬。</p><button class="btn primary" data-action="help-publish">发布需求／提供服务</button></div><p class="muted">不要在公开区填写取件码、手机号或宿舍房号。已关闭和过期信息不再招募。</p><form id="help-filter-form"><div class="form-grid">${filterSelect('类别','service_type',[['','全部类别'],...helpTypes])}${filterSelect('方向','kind',[['','全部方向'],['need','需要帮助'],['offer','提供服务']])}${filterSelect('状态','status',[['open','招募中'],['all','全部状态'],['closed','已关闭'],['expired','已过期']])}${field('搜索','q','search',filters.get('q')||'','maxlength="80" placeholder="搜索互助内容"')}</div><div class="submit-row">${state.me?`<label><input type="checkbox" name="mine" value="1" ${filters.get('mine')==='1'?'checked':''}> 只看我的发布</label>`:''}<button class="btn secondary">筛选</button><button type="button" class="text-button" data-go="help">重置</button><button type="button" class="text-button" data-go="community">返回社区</button></div></form></section><div class="help-feed">${result.items.map(helpCard).join('')||empty('暂无互助信息','可以发布第一条需求，或调整筛选。')}</div>${result.has_more?`<button class="btn secondary full" data-action="help-more" data-cursor="${result.next_cursor}" data-query="${filters.toString()}">加载更多</button>`:''}`,'community');
}
