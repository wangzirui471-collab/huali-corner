import { render, go } from '../core/nav.js';

export const clicks = {'staff-refresh': async()=>render()};

function filterRoute(section, data) {
  const query=new URLSearchParams();
  for (const [key,value] of Object.entries(data)) if(value) query.set(key,value);
  go('staff/'+section+(query.size?'?'+query:''));
}

export const submits = {
  'staff-queue-form': ({form,d})=>filterRoute(form.dataset.section,d),
  'staff-user-form': ({d})=>filterRoute('users',d),
  'staff-audit-form': ({d})=>filterRoute('audit',d),
};
