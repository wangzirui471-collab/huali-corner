// Capture the owner once; queued work cannot borrow a later account's token.
import { state } from './state.js';
import { api } from './http.js';
import { shell, heading, empty, modal, closeModal } from './shell.js';
import { go, render } from './nav.js';
import { date } from './format.js';
import { toast } from './dom.js';
export function context(){
  const user=state.me, session=state.token, epoch=state.renderId;
  const isCurrent=()=>!!user && state.me?.id===user.id && state.token===session;
  return {user,session,config:state.config,isCurrent,isVisible:()=>isCurrent() && epoch===state.renderId,
    request:(path,data)=>{if(!isCurrent())throw new Error('账号已切换，请重新打开页面');return api(path,data,{background:['/draft','/upload','/notifications'].some(prefix=>path.startsWith(prefix))});},
    shell:(html,route)=>{if(isCurrent() && state.renderId===epoch)shell(html,route);},
    heading,empty,modal,closeModal,go,render,date,toast};
}
