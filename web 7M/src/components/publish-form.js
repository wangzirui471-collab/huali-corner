import { unknown } from '../core/draft-config.js';
import { escape, input, select } from './publish-fields.js';
import { control as locationControl } from './locations.js';
export function publishForm(state,deps,{draft=null,restoredLocal=false}={}){const value=state.fields;return `<div class="publish-heading"><div><p class="eyebrow">给闲置一个新去处</p><h1>简单选一选，就能发布</h1><p class="muted">未知可以直说，已知缺陷请如实填写。</p></div><div><button class="btn secondary" data-go="drafts">我的草稿</button> <button class="text-button" data-go="publish/new">新建一条</button></div></div>
      <form id="publish-form" class="simple-publish">
        <div class="draft-toolbar"><span data-testid="draft-status">${draft ? (restoredLocal ? '已恢复本机内容，等待同步' : '已恢复已保存草稿') : '填写后自动保存，草稿建议保留30天'}</span><button type="button" class="text-button" data-draft-save>立即保存</button></div>
        <div class="draft-conflict notice" hidden>未覆盖其他窗口的新版。<button type="button" data-draft-reload>读取新版</button><button type="button" data-draft-copy>另存一份</button></div>
        ${state.source ? '<div class="notice">这是退回物品的重新上架草稿。请重新检查当前缺页、笔记、附件和照片，再确认发布。</div>' : ''}
        <section class="panel"><h2><span class="step-number">1</span> 卖什么，选一下</h2><div class="form-grid">
          ${select('物品类别', 'category', [['books', '二手书'], ['living', '宿舍生活'], ['sports', '运动闲置'], ['electronics', '电子产品']], value.category)}
          ${input('物品／书名 *', 'title', value.title, 'required maxlength="80" placeholder="例如：数据结构 第二版"')}
          ${select('成色', 'condition', ['成色待核对，见实拍', '近乎全新', '正常使用痕迹', '明显磨损，已说明'], value.condition)}
        </div><div class="book-fields" ${value.category === 'books' ? '' : 'hidden'}><div class="form-grid">
          ${select('版次', 'edition', ['版本待确认', '第一版', '第二版', '第三版', '第四版', '第五版', '第六版', '第七版', '第八版', '第九版', ...(value.edition && !['版本待确认','第一版','第二版','第三版','第四版','第五版','第六版','第七版','第八版','第九版'].includes(value.edition) ? [value.edition] : [])], value.edition)}
          ${select('笔记', 'notes', [unknown, '无笔记', '少量笔记', '大量笔记', ...(value.notes && ![unknown,'无笔记','少量笔记','大量笔记'].includes(value.notes) ? [value.notes] : [])], value.notes)}
          ${select('缺页', 'missing', [unknown, '无缺页', '有缺页，见介绍'], value.missing)}
          ${select('附件', 'accessories', [unknown, '原无附件', '无附件', '附件齐全', '附件缺失，见介绍'], value.accessories)}
        </div></div></section>
        <section class="panel"><h2><span class="step-number">2</span> 实拍三张，自动上传</h2><p class="muted photo-count"></p><div class="photo-inputs">
          ${[['front', '正面', '书籍拍封面'], ['side', '侧面', '书籍拍书脊'], ['top', '顶部', '书籍拍书页顶部']].map(([angle, title, tip]) => `<label class="upload-slot"><b>${title}</b><small>${tip}</small><div class="upload-preview" data-preview="${angle}"></div><input type="file" name="${angle}" accept="image/jpeg,image/png,image/webp"></label>`).join('')}
        </div><p class="muted">上传完成后可关窗继续编辑。重复图片不能凑数，图片不代表平台鉴真。</p></section>
        <section class="panel"><h2><span class="step-number">3</span> 定价格，选交付</h2><div class="form-grid">
          ${input('售价（元）*', 'price', value.price, 'type="number" min="0" max="10000" step="0.01" required placeholder="例如12，也可以免费送"')}
          ${select('交付方式', 'delivery', [['pickup', '自提'], ['delivery', '校内送货'], ['both', '自提或送货']], value.delivery)}
          <div class="delivery-fee" ${value.delivery === 'pickup' ? 'hidden' : ''}>${input('送货费（元）', 'delivery_fee', value.delivery_fee, 'type="number" min="0" max="10000" step="0.01"')}</div>
          ${locationControl(deps.config,'region',value.region || value.building + value.point,true,80)}
        </div><p class="muted">地点和费用会展示给买家；具体交付时间在订单中双方确认。</p></section>
        <details class="panel publish-extra"><summary>补充信息与缺陷说明（选填）</summary><label class="field"><span>补充说明／已知缺陷</span><textarea name="description" maxlength="3000" placeholder="不填时只根据已选情况生成介绍，不承诺正版或无瑕疵">${escape(value.description)}</textarea></label><div class="form-grid">
          ${input('出版社（未知可留空）', 'publisher', value.publisher)}${input('作者（可选）', 'author', value.author)}
          ${input('学院（可选）','college',value.college)}${input('适用专业（可选）','major',value.major)}${input('课程（可选）','course',value.course)}${input('ISBN（可选）', 'isbn', value.isbn)}${input('购买月份（不记得可留空）', 'bought', value.bought)}
          ${input('原价（可选，元）', 'original_price', value.original_price, 'type="number" min="0" max="10000" step="0.01"')}
        </div><label class="field"><span>版权页／内页／缺陷补图（可选，全部最多9张）</span><input type="file" name="extra" multiple accept="image/jpeg,image/png,image/webp"></label></details>
        <div class="publish-submit"><span class="muted">当前信誉 ${deps.user.score}/100 · 交易与付款均为模拟</span><button type="submit" class="btn primary">确认发布</button></div>
      </form>`;}
