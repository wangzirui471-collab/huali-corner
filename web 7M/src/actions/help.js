import { api } from '../core/http.js';
import { go, render } from '../core/nav.js';
import { modal, closeModal } from '../core/shell.js';
import { toast } from '../core/dom.js';
import { needLogin } from '../auth/login.js';
import { helpForm, helpCard } from '../components/help.js';
import { ticketModal } from '../pages/support.js';

async function feedback(button,type){
 if(!needLogin())return;
 await ticketModal(type);
 const form=document.getElementById('ticket-form');
 form.dataset.post=button.dataset.id;
 form.querySelector('[name=subject]').value=`校园互助 #${button.dataset.id} ${type==='report'?'举报':'反馈'}`;
}
export const clicks={
 'help-publish':()=>{if(needLogin())modal('<h2>发布校园互助</h2>'+helpForm());},
 'help-status':async button=>{if(!confirm('确认变更这条互助信息？'))return;await api('/help/status',{post_id:Number(button.dataset.id),status:button.dataset.value});await render();},
 'help-report':button=>feedback(button,'report'),
 'help-feedback':button=>feedback(button,'other'),
 'help-more':async button=>{
  button.disabled=true;
  const params=new URLSearchParams(button.dataset.query);params.set('before_id',button.dataset.cursor);
  const result=await api('/help/posts?'+params);
  document.querySelector('.help-feed').insertAdjacentHTML('beforeend',result.items.map(helpCard).join(''));
  if(result.has_more)button.dataset.cursor=result.next_cursor;else button.remove();
 }
};
export const submits={
 'help-post-form':async({form,d})=>{
  const result=await api('/help/posts',{...d,deadline:new Date(d.deadline).getTime()/1000,key:form.dataset.key});
  closeModal();toast('互助信息已发布，可通过私聊协商');go('help/'+result.id);
 },
 'help-filter-form':({fd})=>{const query=new URLSearchParams([...fd].filter(([,value])=>value!==''));go('help?'+query);}
};
