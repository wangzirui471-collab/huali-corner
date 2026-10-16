import { e as escape } from '../core/dom.js';
export function control(config, name, value = '', required = false, maxLength = 150) {
    const groups = config.building_groups || [{name:'已有楼栋',buildings:config.buildings || []}];
    return `<div class="location-control"><label class="field"><span>选择楼栋（也可直接填写下面的位置）</span><select data-location-choice aria-label="选择楼栋"><option value="">自由填写／保留已有位置</option>${groups.map(group => `<optgroup label="${escape(group.name)}">${group.buildings.map(building => `<option value="${escape(building)}">${escape(building)}</option>`).join('')}</optgroup>`).join('')}</select></label><label class="field"><span>公共交付位置／自由填写${required ? ' *' : ''}</span><input name="${escape(name)}" value="${escape(value)}" maxlength="${maxLength}" ${required ? 'required' : ''} placeholder="如C1楼下入口、图书馆南门公共等候区"></label><small>楼栋来自截图，实际名称待核实；请填写公共位置，无需宿舍房号。不申请定位权限。</small></div>`;
  }
