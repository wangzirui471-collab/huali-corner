<script setup>
import { computed, reactive, ref, onScopeDispose } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, roleRank } from '@/shared/legacy/session.js';
import {
  row,
  rows,
  children,
  text,
  number,
  money,
  date,
  statusLabel,
} from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import { newCredential } from '@/features/identity/auth.js';
import { operations } from './actions.js';
import { downloadOperation } from './download.js';
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const downloadController = new AbortController();
onScopeDispose(() => downloadController.abort());
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  section = String(route.params.section || 'overview');
const sections = [
  { key: 'overview', label: '接待概览', rank: 1 },
  { key: 'tickets', label: '工单与退款', rank: 1 },
  { key: 'sessions', label: '客服会话', rank: 1 },
  { key: 'products', label: '商品治理', rank: 1 },
  { key: 'content', label: '内容审核', rank: 1 },
  { key: 'sellers', label: '卖家治理', rank: 1 },
  { key: 'accounts', label: '用户账号', rank: 2 },
  { key: 'staff', label: '人员与权限', rank: 2 },
  { key: 'words', label: '审核词库', rank: 2 },
  { key: 'audit', label: '审计与导出', rank: 1 },
  { key: 'reconcile', label: '模拟账本对账', rank: 1 },
  { key: 'backup', label: '受控备份', rank: 2 },
];
const current = computed(() => sections.find((item) => item.key === section));
const allowed = computed(() => !!current.value && roleRank() >= current.value.rank);
const search = ref(String(route.query.q || '')),
  localFilter = ref('');
const auditFilter = reactive({
  type: String(route.query.type || ''),
  actor: String(route.query.actor || ''),
  since: String(route.query.since || ''),
  until: String(route.query.until || ''),
});
/** 审计参数只包含服务器支持的筛选，列表上限 200，不伪造服务端分页。 */
function auditQuery() {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(auditFilter))
    if (value)
      query.set(
        key,
        ['since', 'until'].includes(key)
          ? String(new Date(value + (key === 'until' ? 'T23:59:59' : 'T00:00:00')).getTime() / 1000)
          : value,
      );
  query.set('limit', '200');
  return query.toString();
}
const data = useLoad(async (signal) => {
  if (!allowed.value || section === 'backup')
    return /** @type {import('@/shared/legacy/dto.js').Row} */ ({});
  const paths = /** @type {Record<string,string>} */ ({
    overview: '/admin',
    tickets: '/tickets',
    sessions: '/support/sessions',
    products: '/product/removed',
    content: '/admin/content',
    sellers: '/admin/sellers',
    accounts: '/admin/accounts?q=' + encodeURIComponent(String(route.query.q || '')),
    staff: '/admin/staff',
    words: '/moderation/words',
    audit: '/audit?' + auditQuery(),
    reconcile: '/reconcile',
  });
  if (section === 'products') {
    const [removed, visible] = await Promise.all([
      api('/product/removed', { signal }),
      api('/products?limit=100&page=1', { signal }),
    ]);
    return { removed: rows(removed), visible: rows(visible) };
  }
  const result = await api(paths[section], { signal });
  return Array.isArray(result) ? { items: rows(result) } : row(result);
});
const items = computed(() =>
  children(data.data.value, 'items').filter(
    (item) =>
      !localFilter.value ||
      Object.values(item).some((value) =>
        String(value).toLowerCase().includes(localFilter.value.toLowerCase()),
      ),
  ),
);
const selected = ref(/** @type {typeof operations[number]|null} */ (null)),
  target = ref(0),
  reason = ref(''),
  confirmed = ref(false),
  role = ref('user'),
  delta = ref(''),
  ticketId = ref(''),
  violation = ref(''),
  password = ref('');
const oneTime = ref(''),
  downloadNotice = ref(''),
  preview = ref('');
const creation = reactive({ open: false, phone: '', nickname: '', role: 'support', password: '' });
const wordForm = reactive({ word: '', category: 'custom', action: 'block' });
/** 进入处置前锁定动作与目标，表单写清业务后果。 @param {string} key 白名单动作。 @param {number} id 目标编号。 */
function openAction(key, id) {
  selected.value = operations.find((item) => item.key === key) || null;
  target.value = id;
  reason.value = '';
  confirmed.value = false;
  delta.value = '';
  ticketId.value = '';
  violation.value = '';
  preview.value = '';
  password.value = '';
}
/** 处置统一二次确认和理由；只向已有 writer 提交，成功后刷新。 */
async function submitAction() {
  await action.run(async () => {
    const operation = selected.value;
    if (!operation || roleRank() < operation.rank) throw new Error('暂无此操作权限');
    if (!confirmed.value || !reason.value.trim()) throw new Error('请填写依据并确认后果');
    const body = /** @type {Record<string,unknown>} */ ({
      [operation.id]: target.value,
      ...operation.extra,
      reason: reason.value,
    });
    if (operation.key === 'role') body.role = role.value;
    if (operation.key === 'stars') {
      body.delta = Number(delta.value);
      if (![-2, -1, 1, 2].includes(Number(delta.value)))
        throw new Error('星级仅可调整 -2、-1、1、2');
    }
    if (operation.key === 'credit') {
      body.ticket_id = Number(ticketId.value);
      body.violation = violation.value || null;
      body.delta = delta.value === '' ? null : Number(delta.value);
      if (!Number.isSafeInteger(body.ticket_id) || !body.ticket_id)
        throw new Error('请填写已核实工单编号');
    }
    if (operation.key === 'password') {
      if (password.value.length < 6) throw new Error('新密码至少 6 位');
      Object.assign(
        body,
        text(session.config, 'auth_mode') === 'client_kdf'
          ? await newCredential(password.value)
          : { password: password.value },
      );
    }
    const result = await api(operation.path, { body });
    if (operation.key === 'password') {
      const response = row(result);
      oneTime.value = '新密码：' + password.value + '\n恢复码：' + text(response, 'recovery_code');
      password.value = '';
    }
    selected.value = null;
    await data.reload();
  }, '处置已由服务端确认');
}
/** 信誉建议仅 dry_run，不以预览替代已核实工单处罚。 */
async function previewCredit() {
  await action.run(async () => {
    if (!violation.value || !ticketId.value) throw new Error('先填写工单编号并选择违规类型');
    const result = row(
      await api('/credit', {
        body: {
          target: target.value,
          ticket_id: Number(ticketId.value),
          violation: violation.value,
          dry_run: true,
          reason: '预览建议',
        },
      }),
    );
    preview.value = `建议扣 ${number(result, 'suggested')} 分，基础 ${number(result, 'base')} + 金额档 ${number(result, 'extra')}；订单 ¥${money(number(result, 'amount'))}`;
    if (!delta.value) delta.value = String(-number(result, 'suggested'));
  }, '已计算建议，尚未执行处罚');
}
/** 显式创建运营账号，口令不存储；恢复码留在一次性弹窗。 */
async function createStaff() {
  await action.run(async () => {
    if (creation.password.length < 6) throw new Error('密码至少 6 位');
    const credential =
      text(session.config, 'auth_mode') === 'client_kdf'
        ? await newCredential(creation.password)
        : { password: creation.password };
    const result = row(
      await api('/admin/staff', {
        body: {
          phone: creation.phone,
          nickname: creation.nickname,
          role: creation.role,
          ...credential,
        },
      }),
    );
    oneTime.value = '账号：' + creation.phone + '\n恢复码：' + text(result, 'recovery_code');
    creation.password = '';
    creation.open = false;
    await data.reload();
  }, '运营账号已创建');
}
/** 词库增删停用走明确 op，内部命中信息只在工作台展示。 @param {string} op 动作。 @param {string} [word] 词条。 */
async function wordAction(op, word = wordForm.word) {
  if (
    op !== 'add' &&
    !window.confirm(
      '确认' + (op === 'remove' ? '停用' : '恢复') + '词条「' + word + '」？立即影响审核。',
    )
  )
    return;
  await action.run(async () => {
    await api('/moderation/words', {
      body: { op, word, category: wordForm.category, action: wordForm.action },
    });
    if (op === 'add') wordForm.word = '';
    await data.reload();
  }, '审核词库已更新');
}
/** URL 保存查询，账号搜索只由用户明确提交触发。 */
function searchAccounts() {
  void router.push({ query: { q: search.value || undefined } });
}
/** 审计筛选采用服务端真实参数，最多展示 200 条并可按同条件导出。 */
function filterAudit() {
  void router.push({ query: { ...auditFilter } });
}
/** 受控下载必须经说明后显式点击；备份不会被页面挂载自动触发。 @param {'audit'|'backup'} kind 类型。 */
async function download(kind) {
  if (
    kind === 'backup' &&
    !window.confirm(
      '备份包含凭据与私密媒体，请仅保存到受控目录，不放入 Git。生成后仍须在隔离环境恢复验证。确认生成？',
    )
  )
    return;
  await action.run(async () => {
    downloadNotice.value = await downloadOperation(kind, auditQuery(), downloadController.signal);
  }, '服务端下载操作已完成');
}
/** 客服认领失败保留队列，不跳转到不可接待的会话。 @param {number} id 会话编号。 */
async function claim(id) {
  await action.run(async () => {
    const result = row(await api('/support/claim', { body: { room_id: id } }));
    if (!result.ok) throw new Error('该会话已由其他客服接入');
    await router.push('/messages/' + id);
  });
}
</script>
<template>
  <div class="workspace-layout">
    <aside class="panel workspace-nav">
      <RouterLink to="/me">← 我的转角</RouterLink>
      <h2>平台工作台</h2>
      <p class="muted">{{ text(session.me, 'nickname') }} · {{ text(session.me, 'role') }}</p>
      <nav aria-label="工作台分区">
        <RouterLink
          v-for="item in sections.filter((entry) => roleRank() >= entry.rank)"
          :key="item.key"
          :to="'/workspace/' + item.key"
          :aria-current="section === item.key ? 'page' : undefined"
          >{{ item.label }}</RouterLink
        >
      </nav>
    </aside>
    <section class="workspace-content">
      <header class="section-heading">
        <div>
          <span class="eyebrow">WORKSPACE</span>
          <h1>{{ current?.label || '分区不存在' }}</h1>
        </div>
        <AppButton
          v-if="allowed && section !== 'backup'"
          variant="secondary"
          :loading="data.loading.value"
          @click="data.reload"
          >刷新</AppButton
        >
      </header>
      <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
      <p v-if="!allowed" class="notice-panel">暂无此分区权限，请从左侧选择可访问入口。</p>
      <LoadBoundary
        v-else
        :loading="data.loading.value"
        :error="data.error.value"
        :forbidden="data.forbidden.value"
        @retry="data.reload"
        ><template v-if="section === 'overview'"
          ><div class="account-tiles">
            <RouterLink to="/workspace/tickets">处理工单 ↗</RouterLink
            ><RouterLink to="/workspace/sessions">接待客服会话 ↗</RouterLink
            ><RouterLink to="/workspace/products">商品审核 ↗</RouterLink
            ><RouterLink to="/workspace/content">内容治理 ↗</RouterLink>
          </div>
          <section class="panel">
            <h2>群管理员申请</h2>
            <article
              v-for="item in children(data.data.value, 'nominations')"
              :key="number(item, 'id')"
              class="list-row"
            >
              <div>
                <b>{{ text(item, 'nickname') }} · 群 #{{ number(item, 'room_id') }}</b>
                <p>{{ text(item, 'reason') }}</p>
                <small>{{ statusLabel(text(item, 'status')) }}</small>
              </div>
              <AppButton
                v-if="text(session.me, 'role') === 'admin' && text(item, 'status') === 'pending'"
                variant="secondary"
                @click="openAction('nominate', number(item, 'id'))"
                >审核任命</AppButton
              >
            </article>
            <p v-if="!children(data.data.value, 'nominations').length" class="muted">暂无申请</p>
          </section></template
        >
        <template v-else-if="section === 'tickets'"
          ><p class="muted">退款、内部备注、复核和利益冲突校验在工单详情处理。</p>
          <article v-for="item in items" :key="number(item, 'id')" class="panel list-row">
            <div>
              <RouterLink :to="'/support/' + number(item, 'id')"
                ><b>#{{ number(item, 'id') }} {{ text(item, 'subject') }}</b></RouterLink
              >
              <p>
                {{ text(item, 'type') }} · {{ statusLabel(text(item, 'status')) }} ·
                {{ date(number(item, 'created')) }}
              </p>
            </div>
            <RouterLink :to="'/support/' + number(item, 'id')">进入处理 →</RouterLink>
          </article></template
        >
        <template v-else-if="section === 'sessions'"
          ><article v-for="item in items" :key="number(item, 'id')" class="panel list-row">
            <div>
              <b>{{ text(item, 'customer_name') }} · {{ text(item, 'subject') }}</b>
              <p>{{ text(item, 'last_body') }}</p>
              <small>{{ text(item, 'online_hint') }} · 等待 {{ number(item, 'waiting') }} 秒</small>
            </div>
            <AppButton :loading="action.busy.value" @click="claim(number(item, 'id'))">{{
              number(item, 'assignee') ? '接入会话' : '认领并接入'
            }}</AppButton>
          </article>
          <p v-if="!items.length" class="panel muted">暂无进行中的客服会话。</p></template
        >
        <template v-else-if="section === 'products'"
          ><p class="muted">列出最近 100 件公开商品与已下架商品；管理操作由原服务复核权限。</p>
          <section
            v-for="group in [
              { key: 'removed', label: '下架与复核' },
              { key: 'visible', label: '当前公开商品' },
            ]"
            :key="group.key"
          >
            <h2>{{ group.label }}</h2>
            <article
              v-for="item in children(data.data.value, group.key)"
              :key="number(item, 'id')"
              class="panel"
            >
              <div class="list-row">
                <RouterLink :to="'/products/' + number(item, 'id')"
                  >#{{ number(item, 'id') }} {{ text(item, 'title') }}</RouterLink
                ><span>¥{{ money(number(item, 'price')) }}</span>
              </div>
              <p class="muted">{{ text(item, 'review_reason') || text(item, 'removed_reason') }}</p>
              <div class="actions">
                <AppButton
                  v-if="group.key === 'visible'"
                  variant="secondary"
                  @click="openAction('delist', number(item, 'id'))"
                  >强制下架</AppButton
                ><AppButton
                  v-if="group.key === 'removed' && roleRank() >= 2"
                  variant="secondary"
                  @click="openAction('restore', number(item, 'id'))"
                  >复核恢复</AppButton
                ><AppButton variant="quiet" @click="openAction('approve', number(item, 'id'))"
                  >审核通过</AppButton
                ><AppButton variant="quiet" @click="openAction('reject', number(item, 'id'))"
                  >驳回</AppButton
                >
              </div>
            </article>
          </section></template
        >
        <template v-else-if="section === 'content'"
          ><section
            v-for="group in [
              { key: 'posts', label: '帖子', kind: 'post' },

              { key: 'messages', label: '消息', kind: 'message' },
            ]"
            :key="group.key"
          >
            <h2>{{ group.label }}</h2>
            <article
              v-for="item in children(data.data.value, group.key)"
              :key="number(item, 'id')"
              class="panel"
            >
              <b>#{{ number(item, 'id') }} {{ text(item, 'nickname') }}</b>
              <p class="description">{{ text(item, 'body') }}</p>
              <p class="muted">
                审核命中：{{
                  item.moderation ? JSON.stringify(item.moderation) : text(item, 'review_reason')
                }}
              </p>
              <div class="actions">
                <div>
                  <AppButton
                    variant="secondary"
                    @click="openAction(group.kind + '-remove', number(item, 'id'))"
                    >移除</AppButton
                  ><AppButton
                    v-if="roleRank() >= 2"
                    variant="quiet"
                    @click="openAction(group.kind + '-restore', number(item, 'id'))"
                    >恢复</AppButton
                  >
                </div>
                <RouterLink
                  v-if="group.kind === 'message'"
                  :to="'/messages/' + number(item, 'room_id')"
                  >进入所属会话处理</RouterLink
                >
              </div>
            </article>
          </section></template
        >
        <template v-else-if="['accounts', 'staff', 'sellers'].includes(section)"
          ><form v-if="section === 'accounts'" class="inline-form" @submit.prevent="searchAccounts">
            <label>按昵称或账号查找<input v-model="search" maxlength="120" type="search" /></label
            ><AppButton type="submit" variant="secondary">查询</AppButton>
          </form>
          <div class="actions">
            <AppButton v-if="section === 'staff'" @click="creation.open = true"
              >创建运营账号</AppButton
            ><label>筛选当前结果<input v-model="localFilter" type="search" /></label>
          </div>
          <p class="muted">
            服务器有界返回：账号最多 300 条、卖家最多 200 条。更精确的账号结果请使用上方搜索。
          </p>
          <article v-for="item in items" :key="number(item, 'id')" class="panel">
            <div class="list-row">
              <div>
                <h2>
                  {{ text(item, 'nickname') }} <small>#{{ number(item, 'id') }}</small>
                </h2>
                <p>
                  {{ text(item, 'phone') }} · {{ text(item, 'role_name') || text(item, 'role') }} ·
                  {{ text(item, 'status') || text(item, 'user_status') }}
                </p>
                <p v-if="section === 'sellers'">
                  在售 {{ number(item, 'available') }} / 下架 {{ number(item, 'removed') }} / 总数
                  {{ number(item, 'total') }}
                </p>
                <small
                  >信誉 {{ number(item, 'score') }} · 当前会话 {{ number(item, 'sessions') }}</small
                >
              </div>
              <RouterLink v-if="roleRank() >= 2" :to="'/workspace/users/' + number(item, 'id')"
                >查看档案 →</RouterLink
              >
            </div>
            <div v-if="number(item, 'id') !== number(session.me, 'id')" class="actions">
              <AppButton
                v-if="section === 'sellers'"
                variant="secondary"
                @click="openAction('seller', number(item, 'id'))"
                >批量下架在售商品</AppButton
              ><AppButton variant="quiet" @click="openAction('revoke', number(item, 'id'))"
                >强制下线</AppButton
              ><template v-if="roleRank() >= 2"
                ><AppButton
                  v-if="section === 'staff'"
                  variant="quiet"
                  @click="
                    openAction(
                      text(item, 'status') === 'active' ? 'disable' : 'enable',
                      number(item, 'id'),
                    )
                  "
                  >{{ text(item, 'status') === 'active' ? '停用' : '启用' }}</AppButton
                ><AppButton
                  v-if="section === 'staff'"
                  variant="quiet"
                  @click="openAction('password', number(item, 'id'))"
                  >重置密码</AppButton
                ><AppButton variant="quiet" @click="openAction('role', number(item, 'id'))"
                  >角色</AppButton
                ><AppButton variant="quiet" @click="openAction('credit', number(item, 'id'))"
                  >信誉</AppButton
                ><AppButton variant="quiet" @click="openAction('stars', number(item, 'id'))"
                  >星级</AppButton
                ><AppButton
                  variant="quiet"
                  @click="
                    openAction(
                      text(item, 'status') === 'banned' ? 'unban' : 'ban',
                      number(item, 'id'),
                    )
                  "
                  >{{ text(item, 'status') === 'banned' ? '解封' : '封禁' }}</AppButton
                ><AppButton variant="quiet" @click="openAction('purge', number(item, 'id'))"
                  >清除登录信息</AppButton
                ></template
              >
            </div>
          </article></template
        >
        <template v-else-if="section === 'words'"
          ><form class="panel form-grid" @submit.prevent="wordAction('add')">
            <label>词条<input v-model="wordForm.word" required maxlength="40" /></label
            ><label>分类<input v-model="wordForm.category" required maxlength="40" /></label
            ><label
              >命中动作<select v-model="wordForm.action">
                <option value="block">阻止</option>
                <option value="review">待审核</option>
                <option value="report">仅记录</option>
              </select></label
            ><AppButton type="submit" :loading="action.busy.value">添加词条</AppButton>
          </form>
          <p>
            共 {{ number(data.data.value, 'total') }} 条，内置
            {{ number(data.data.value, 'builtin_count') }} 条。
          </p>
          <article
            v-for="item in children(data.data.value, 'words')"
            :key="text(item, 'word')"
            class="panel list-row"
          >
            <span
              >{{ text(item, 'word') }} · {{ text(item, 'category') }} ·
              {{ text(item, 'action') }}</span
            ><AppButton variant="quiet" @click="wordAction('remove', text(item, 'word'))"
              >停用</AppButton
            >
          </article>
          <h2>已停用内置词条（自建词条停用即删除，可重新添加）</h2>
          <div
            v-for="word in Array.isArray(data.data.value?.disabled) ? data.data.value.disabled : []"
            :key="String(word)"
            class="list-row"
          >
            <span>{{ word }}</span
            ><AppButton variant="quiet" @click="wordAction('restore', String(word))"
              >恢复</AppButton
            >
          </div></template
        >
        <template v-else-if="section === 'audit'"
          ><form class="panel form-grid" @submit.prevent="filterAudit">
            <label
              >事件类型<input v-model="auditFilter.type" placeholder="如 credit、backup" /></label
            ><label>操作人编号<input v-model="auditFilter.actor" inputmode="numeric" /></label
            ><label>开始日期<input v-model="auditFilter.since" type="date" /></label
            ><label>结束日期<input v-model="auditFilter.until" type="date" /></label>
            <div class="actions full-width">
              <AppButton type="submit" variant="secondary">应用筛选</AppButton
              ><AppButton variant="quiet" :loading="action.busy.value" @click="download('audit')"
                >按此条件导出 CSV</AppButton
              >
            </div>
          </form>
          <p class="muted">列表最多 200 条，导出范围以服务端上限为准。</p>
          <article v-for="item in items" :key="number(item, 'id')" class="panel">
            <b>{{ text(item, 'type') || text(item, 'kind') }} · #{{ number(item, 'id') }}</b>
            <p>{{ text(item, 'reason') }}</p>
            <small
              >操作人 #{{ number(item, 'actor') }} → 目标 #{{ number(item, 'target') }} ·
              {{ date(number(item, 'created')) }}</small
            >
          </article></template
        >
        <template v-else-if="section === 'reconcile'"
          ><p class="notice-panel">仅核对模拟账本，当前页面不修改账本、数据库或资金。</p>
          <article v-for="item in items" :key="number(item, 'id')" class="panel">
            <RouterLink to="/orders">订单 #{{ number(item, 'id') }}</RouterLink>
            <dl class="detail-facts">
              <dt>付款</dt>
              <dd>¥{{ money(number(item, 'payment')) }}</dd>
              <dt>退款</dt>
              <dd>¥{{ money(number(item, 'refund')) }}</dd>
              <dt>净结算</dt>
              <dd>¥{{ money(number(item, 'net_settlement')) }}</dd>
              <dt>托管</dt>
              <dd>¥{{ money(number(item, 'held')) }}</dd>
              <dt>结果</dt>
              <dd>{{ item.consistent ? '一致' : '存在差异，请核对' }}</dd>
            </dl>
          </article></template
        >
        <section v-else-if="section === 'backup'" class="panel">
          <h2>生成私密备份</h2>
          <p>备份可能包含凭据、个人资料和私密媒体。请保存在受控目录，不上传 Git 或公共网盘。</p>
          <p>
            只调用当前隔离后端已有备份入口。Worker 返回
            ZIP；本地后端可能返回服务器私密保存路径。超过服务端限制时停止并显示错误。
          </p>
          <p>备份文件生成不等于恢复验收通过。恢复必须在确认权威库和独立目标后另行演练。</p>
          <AppButton :loading="action.busy.value" @click="download('backup')"
            >阅读说明并生成备份</AppButton
          >
        </section>
        <p v-if="downloadNotice" class="notice-panel">{{ downloadNotice }}</p>
        <p
          v-if="
            !['overview', 'products', 'content', 'words', 'backup'].includes(section) &&
            !items.length
          "
          class="panel muted"
        >
          当前条件没有记录。
        </p></LoadBoundary
      >
    </section>
  </div>
  <AppDialog
    :open="!!selected"
    :title="selected?.label || '处置确认'"
    @close="!action.busy.value && (selected = null)"
    ><form v-if="selected" class="form-stack" @submit.prevent="submitAction">
      <p class="notice-panel">{{ selected.consequence }}</p>
      <p>目标编号 #{{ target }}。权限、归属和关联关系由服务端复核。</p>
      <TaskFeedback :error="action.error.value" /><label v-if="selected.key === 'role'"
        >新角色<select v-model="role">
          <option value="user">普通用户</option>
          <option value="support">客服</option>
          <option v-if="roleRank() === 3" value="admin">管理员</option>
          <option v-if="roleRank() === 3" value="developer">开发者</option>
        </select></label
      ><label v-if="selected.key === 'password'"
        >新临时密码<input
          v-model="password"
          type="password"
          required
          minlength="6"
          autocomplete="new-password" /></label
      ><template v-if="selected.key === 'credit'"
        ><label>已核实工单编号<input v-model="ticketId" required inputmode="numeric" /></label
        ><label
          >违规类型<select v-model="violation">
            <option value="">手填分值</option>
            <option value="minor">轻微</option>
            <option value="moderate">中度</option>
            <option value="severe">严重</option>
          </select></label
        ><AppButton variant="quiet" @click="previewCredit">只预览建议分值</AppButton>
        <p v-if="preview">{{ preview }}</p></template
      ><label v-if="['credit', 'stars'].includes(selected.key)"
        >{{ selected.key === 'credit' ? '信誉分变化（扣分填负数）' : '星级变化（-2、-1、1、2）'
        }}<input
          v-model="delta"
          type="number"
          step="1"
          :required="selected.key === 'stars' || !violation" /></label
      ><label>依据与理由<textarea v-model="reason" required maxlength="500" rows="4" /></label
      ><label class="checkbox-line"
        ><input
          v-model="confirmed"
          type="checkbox"
          required
        />我已核对目标与依据，并了解上述后果。</label
      ><AppButton type="submit" :loading="action.busy.value">确认执行</AppButton>
    </form></AppDialog
  >
  <AppDialog
    :open="creation.open"
    title="创建运营账号"
    @close="!action.busy.value && (creation.open = false)"
    ><TaskFeedback :error="action.error.value" />
    <form class="form-stack" @submit.prevent="createStaff">
      <label>账号<input v-model="creation.phone" required autocomplete="off" /></label
      ><label>昵称<input v-model="creation.nickname" required maxlength="24" /></label
      ><label
        >角色<select v-model="creation.role">
          <option value="support">客服</option>
          <option v-if="roleRank() === 3" value="admin">管理员</option>
          <option v-if="roleRank() === 3" value="developer">开发者</option>
        </select></label
      ><label
        >初始密码<input
          v-model="creation.password"
          type="password"
          required
          minlength="6"
          autocomplete="new-password" /></label
      ><AppButton type="submit" :loading="action.busy.value">创建并显示恢复码</AppButton>
    </form></AppDialog
  ><AppDialog :open="!!oneTime" title="一次性凭据信息" @close="oneTime = ''"
    ><p>请通过可信渠道交给本人并提醒首次登录改密，不保存到公共文档。</p>
    <pre class="recovery-code">{{ oneTime }}</pre>
    <AppButton @click="oneTime = ''">我已保存</AppButton></AppDialog
  >
</template>
