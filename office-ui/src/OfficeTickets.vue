<script setup>
/** L1 工单办公：真实明细、逐单草稿、人工核对和可重试的确认回执。 */
import { computed, onMounted, ref } from 'vue';
import { ElAlert, ElButton, ElCheckbox, ElDialog, ElInput, ElOption, ElSelect } from 'element-plus';

const props = defineProps({ api: Function, initial: Object, authorized: Function, close: Function });
const rows = ref([]), total = ref(0), page = ref(1), hasMore = ref(false);
const status = ref('open'), busy = ref(false), error = ref(''), notice = ref('');
const batchLimit = ref(1);
const proposal = ref(null), receipt = ref(null);
const labels = { reply: '仅回复', claim_reply: '受理并回复', review_reply: '提交复核并回复', resolve_reply: '回复并结案' };
const states = { open: '待处理', processing: '处理中', review: '待复核', resolved: '已解决' };
const selected = computed(() => rows.value.filter(row => row.selected && row.can_process));
const editable = computed(() => !busy.value && !proposal.value);

/** 接收服务器分页快照，清除上一页的选中项与执行计划。 */
function acceptList(data){
  rows.value = data.tickets.map(row => ({ ...row, selected: false, draft_body: '',
    action: 'claim_reply', reason: '' }));
  total.value = data.total; page.value = data.page; hasMore.value = data.has_more;
  batchLimit.value = data.batch_limit || 1;
  proposal.value = null;
}

/** 执行单个界面操作，防止重复点击并校验登录者尚有 L1 身份。 */
async function run(task){
  if (busy.value) return;
  if (!props.authorized()) { props.close(); return; }
  busy.value = true; error.value = '';
  try { await task(); }
  catch (err) {
    error.value = err.message || '操作失败，请稍后重试';
    if ([400, 403, 404, 409].includes(err.status)) proposal.value = null;
  }
  finally { busy.value = false; }
}

/** 读取真实待办，状态筛选和分页均由后端控制。 */
async function load(next = 1){
  await run(async () => acceptList(await props.api('/ai/office/tickets/list', { page: next, status: status.value })));
}

/** 只选本页有处理权限的工单；跨页不会隐式选中。 */
function selectPage(){
  const all = rows.value.filter(row => row.can_process).every(row => row.selected);
  rows.value.forEach(row => { row.selected = row.can_process && !all; });
}

/** 为选中的每张工单生成可编辑草稿，不直接发给客户。 */
async function draft(){
  await run(async () => {
    const result = await props.api('/ai/office/tickets/draft', {
      ticket_ids: selected.value.map(row => row.id),
      revisions: Object.fromEntries(selected.value.map(row => [String(row.id), row.revision]))
    });
    result.items.forEach(item => {
      const row = rows.value.find(row => row.id === item.id);
      if (row) Object.assign(row, { draft_body: item.body, reason: item.reason, action: item.action, revision: item.revision });
    });
    notice.value = result.mode === 'llm' ? 'AI 草稿已生成，尚未发送。请逐条核对正文和处理依据。'
      : '模型暂不可用，已生成基础受理草稿。请补充核实结果，尚未发送。';
  });
}

/** 保存当前可见的具体计划，随后锁定编辑，避免确认的内容与预览不一致。 */
async function prepare(){
  await run(async () => {
    proposal.value = await props.api('/ai/office/tickets/prepare', { items: selected.value.map(row => ({
      id: row.id, revision: row.revision, action: row.action, body: row.draft_body, reason: row.reason
    })) });
    receipt.value = null;
  });
}

/** 明确展示影响后再次确认；网络结果未知时保留同一编号供安全重试。 */
async function execute(){
  if (busy.value || !proposal.value) return;
  const count = proposal.value.items.length;
  if (!window.confirm(`确认按当前计划处理 ${count} 条工单？\n公开回复将发送给用户，所选结案动作会结束工单。`)) return;
  await run(async () => {
    receipt.value = await props.api('/ai/office/tickets/confirm', {
      proposal_id: proposal.value.proposal_id, confirmed: true
    });
    proposal.value = null;
    acceptList(await props.api('/ai/office/tickets/list', { page: 1, status: status.value }));
  });
}

/** 等待组件挂载后使用现有查询结果，直接进入真实明细。 */
onMounted(() => {
  if (props.initial?.tickets) acceptList(props.initial);
  else load();
});
</script>

<template>
  <ElDialog class="hc-office" :model-value="true" title="工单办公 · L1" width="min(1040px, calc(100vw - 20px))"
    :close-on-click-modal="false" :before-close="() => { if (!busy) props.close(); }" @closed="props.close">
    <p class="hc-office-intro">读取真实工单，核对后受理、回复或提交复核。受理不等于解决；退款、处罚和申诉请到工作台核实。</p>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <ElAlert v-if="receipt" :title="receipt.message" type="success" :closable="false" show-icon />
    <ElAlert v-if="notice" :title="notice" type="info" :closable="false" />
    <div class="hc-office-toolbar">
      <ElSelect v-model="status" aria-label="工单状态" :disabled="!editable" @change="load(1)">
        <ElOption label="待处理" value="open" /><ElOption label="处理中" value="processing" />
        <ElOption label="待复核" value="review" /><ElOption label="全部未结束" value="all" />
      </ElSelect>
      <ElButton :disabled="!editable" @click="load(1)">刷新明细</ElButton>
      <ElButton :disabled="!editable || !rows.length" @click="selectPage">选择本页可处理项</ElButton>
      <span>共 {{ total }} 条 · 第 {{ page }} 页 · 已选 {{ selected.length }} 条 · 每批最多 {{ batchLimit }} 条</span>
    </div>
    <p v-if="!rows.length && !busy" class="hc-office-empty">当前筛选没有工单。</p>
    <article v-for="row in rows" :key="row.id" class="hc-office-ticket" :data-ticket-id="row.id">
      <header>
        <ElCheckbox v-model="row.selected" :disabled="!editable || !row.can_process" :aria-label="`选择工单 ${row.id}`" />
        <b>#{{ row.id }} · {{ row.subject }}</b><span>{{ states[row.status] || row.status }}</span>
        <a :href="`#ticket/${row.id}`">工作台查看 →</a>
      </header>
      <p class="hc-office-body">{{ row.body }}</p>
      <details v-if="row.messages.length"><summary>最近公开补充（{{ row.messages.length }} 条）</summary>
        <p v-for="message in row.messages" :key="message.id" class="hc-office-body">{{ message.body }}</p>
      </details>
      <p v-if="!row.can_process" class="hc-office-blocked">{{ row.blocked_reason }}</p>
      <div v-if="row.selected" class="hc-office-editor">
        <label>处理动作
          <ElSelect v-model="row.action" :disabled="!editable" :aria-label="`工单 ${row.id} 处理动作`">
            <ElOption v-for="action in row.allowed_actions" :key="action" :label="labels[action]" :value="action" />
          </ElSelect>
        </label>
        <label>公开回复（发送前请核对）
          <ElInput v-model="row.draft_body" type="textarea" :rows="3" maxlength="2000" show-word-limit
            :disabled="!editable" :aria-label="`工单 ${row.id} 公开回复`" />
        </label>
        <label>处理依据（会写入审计）
          <ElInput v-model="row.reason" type="textarea" :rows="2" maxlength="1000" :disabled="!editable"
            :aria-label="`工单 ${row.id} 处理依据`" />
        </label>
      </div>
    </article>
    <div class="hc-office-toolbar">
      <ElButton :disabled="!editable || page <= 1" @click="load(page - 1)">上一页</ElButton>
      <ElButton :disabled="!editable || !hasMore" @click="load(page + 1)">下一页</ElButton>
      <span v-if="hasMore">还有更多工单，本次只处理当前勾选项。</span>
    </div>
    <template #footer>
      <div class="hc-office-footer">
        <template v-if="!proposal">
          <ElButton :loading="busy" :disabled="!selected.length || busy" @click="draft">生成逐单回复草稿</ElButton>
          <ElButton type="primary" :loading="busy" :disabled="!selected.length || busy" @click="prepare">核对并预览执行计划</ElButton>
        </template>
        <template v-else>
          <b>待执行 {{ proposal.items.length }} 条 · 10 分钟内有效</b>
          <ElButton :disabled="busy" @click="proposal = null">返回修改</ElButton>
          <ElButton type="danger" :loading="busy" :disabled="busy" @click="execute">确认执行</ElButton>
        </template>
      </div>
    </template>
  </ElDialog>
</template>

<style>
.hc-office{--el-color-primary:#8064ae;--el-color-danger:#b23835;--el-border-radius-base:8px;color:#35313f;max-height:90dvh;display:flex;flex-direction:column;margin-top:5dvh!important}
.hc-office .el-dialog__body{overflow:auto;padding-top:4px;overscroll-behavior:contain}
.hc-office .el-button--primary{--el-button-bg-color:#ffcc38;--el-button-border-color:#efbd2d;--el-button-text-color:#45360b;--el-button-hover-bg-color:#ffe07b;--el-button-hover-text-color:#45360b}
.hc-office-intro{font-size:13px;line-height:1.7;color:#726b80}
.hc-office-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0;font-size:12px}
.hc-office-toolbar .el-select{width:155px}
.hc-office-ticket{padding:14px;border:1px solid #e8e2f0;border-radius:12px;margin:10px 0;background:#fff}
.hc-office-ticket header{display:flex;align-items:center;flex-wrap:wrap;gap:10px;line-height:1.6}
.hc-office-ticket header span{color:#786294;font-size:12px}
.hc-office-ticket header a{margin-left:auto;color:#8064ae;font-size:12px}
.hc-office-body{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.7}
.hc-office-editor{display:grid;gap:12px;padding-top:10px}
.hc-office-editor label{display:grid;gap:6px;font-size:12px}
.hc-office-blocked{font-size:12px;color:#a13e35}
.hc-office-footer{display:flex;justify-content:flex-end;align-items:center;flex-wrap:wrap;gap:8px}
.hc-office .el-alert{margin:8px 0}.hc-office-empty{padding:36px;text-align:center;color:#837a91}
@media(max-width:600px){.hc-office{max-height:96dvh;margin-top:2dvh!important;padding:14px}.hc-office-ticket{padding:10px}.hc-office-footer{justify-content:stretch}.hc-office-footer .el-button{flex:1;margin-left:0}.hc-office-ticket header a{margin-left:0}}
</style>
