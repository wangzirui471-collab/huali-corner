<script setup>
import { computed, reactive, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, roleRank } from '@/shared/legacy/session.js';
import {
  row,
  rows,
  text,
  number,
  children,
  date,
  money,
  statusLabel,
} from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
// 本机FAQ经新FastAPI；线上宠物流构建保留原AI后端，避免请求尚未发布的本机端口。
const localFaqEnabled = import.meta.env.VITE_HUALI_ASSISTANT_MODE !== 'legacy-stream';
import AppButton from '@/shared/ui/AppButton.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import { yuanToCents } from '@/features/trade/checkout.js';
import AssistantPanel from './assistant/AssistantPanel.vue';
import { consumeAssistantDraft } from './assistant/handoff-draft.js';
const route = useRoute(),
  router = useRouter(),
  action = useAction();
const creating = route.path.endsWith('/new'),
  id = Number(route.params.id) || 0;
const form = reactive({
  type: String(route.query.type || 'other'),
  subject: '',
  body: creating ? consumeAssistantDraft() : '',
  order_id: String(route.query.order || ''),
  product_id: Number(route.query.product) || 0,
  reason: '',
  internal: false,
  amount: '',
  link: '',
});
const outcome = ref('claim'),
  filter = ref('');
const tickets = useLoad(async (signal) => rows(await api('/tickets', { signal })));
const detail = useLoad(async (signal) =>
  id ? row(await api('/ticket?id=' + id, { signal })) : null,
);
const order = useLoad(async (signal) => {
  if (!id) return null;
  const ticket = row(await api('/ticket?id=' + id, { signal }));
  return number(ticket, 'order_id')
    ? row(await api('/order?id=' + number(ticket, 'order_id'), { signal }))
    : null;
});
const history = useLoad(async (signal) =>
  !id && !creating ? rows(await api('/credit/history', { signal })) : [],
);
const candidates = ref(/** @type {import('@/shared/legacy/dto.js').Row[]} */ ([]));
const visible = computed(() =>
  (tickets.data.value || []).filter(
    (ticket) => !filter.value || text(ticket, 'status') === filter.value,
  ),
);
const staff = computed(() => roleRank() >= 1);
const conflict = computed(
  () =>
    number(detail.data.value, 'user_id') === number(session.me, 'id') ||
    (!!order.data.value &&
      [number(order.data.value, 'buyer_id'), number(order.data.value, 'seller_id')].includes(
        number(session.me, 'id'),
      )),
);
/** 提交工单后才跳转，失败保留全部填写内容。 */
async function create() {
  await action.run(async () => {
    const result = row(
      await api('/tickets', {
        body: {
          type: form.type,
          subject: form.subject,
          body: form.body,
          order_id: Number(form.order_id) || null,
          product_id: form.product_id || null,
        },
      }),
    );
    await router.push('/support/' + number(result, 'id'));
  }, '工单已提交');
}
/** 内部备注仅平台人员可提交，用户页面不渲染该选项。 */
async function reply() {
  await action.run(async () => {
    await api('/ticket/reply', {
      body: { id, body: form.body, internal: staff.value && form.internal },
    });
    form.body = '';
    await detail.reload();
  }, '回复已发送');
}
/** 每次处置须写依据；部分退款以整数分提交，最终权限和利益冲突由后端检查。 */
async function resolve() {
  await action.run(async () => {
    if (conflict.value) throw new Error('不能处理自己提交或参与交易的工单');
    await api('/ticket/resolve', {
      body: {
        id,
        outcome: outcome.value,
        reason: form.reason,
        ...(outcome.value === 'refund'
          ? { amount: form.amount ? yuanToCents(form.amount) : number(order.data.value, 'total') }
          : {}),
      },
    });
    form.reason = '';
    await detail.reload();
    await order.reload();
  }, '处理结果已记录');
}
/** 先展示服务端提供的可关联订单，禁止猜测无关订单号。 */
async function loadCandidates() {
  await action.run(async () => {
    candidates.value = rows(await api('/ticket/candidates?id=' + id));
  }, '请选择与当事人有关的订单');
}
/** 关联订单后刷新证据上下文。 */
async function linkOrder() {
  await action.run(async () => {
    await api('/ticket/link-order', { body: { id, order_id: Number(form.link) } });
    await detail.reload();
    await order.reload();
    candidates.value = [];
  }, '关联订单已更新');
}
/** 在线客服只在具体工单上下文开启。 */
async function contact() {
  await action.run(async () => {
    const result = row(await api('/support/room', { body: { ticket_id: id } }));
    await router.push('/messages/' + number(result, 'id'));
  });
}
</script>
<template>
  <header class="section-heading">
    <div>
      <span class="eyebrow">WE ARE HERE TO HELP</span>
      <h1>{{ creating ? '提交问题' : id ? '工单 #' + id : '帮助与售后' }}</h1>
      <p class="muted">客服服务时间 08:00—20:00。非工作时间仍可留言；资金均为模拟。</p>
    </div>
    <RouterLink :to="id || creating ? '/support' : '/support/new'">{{
      id || creating ? '返回工单列表' : '提交问题'
    }}</RouterLink>
  </header>
  <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
  <form v-if="creating" class="panel form-stack narrow-panel" @submit.prevent="create">
    <label
      >问题类型<select v-model="form.type">
        <option value="other">咨询</option>
        <option value="refund">售后退款</option>
        <option value="report">举报</option>
        <option value="appeal">申诉</option>
        <option value="reschedule">改约</option>
      </select></label
    ><label>标题<input v-model="form.subject" required maxlength="120" /></label
    ><label>订单编号（可选）<input v-model="form.order_id" inputmode="numeric" /></label
    ><label>详细说明<textarea v-model="form.body" required maxlength="3000" rows="7" /></label>
    <p class="muted">说明事实、时间与希望解决的问题。举报不会直接扣分；处罚必须经过核查。</p>
    <AppButton type="submit" :loading="action.busy.value">提交工单</AppButton>
  </form>
  <LoadBoundary
    v-else-if="id"
    :loading="detail.loading.value"
    :error="detail.error.value"
    :forbidden="detail.forbidden.value"
    @retry="detail.reload"
    ><div v-if="detail.data.value" class="case-layout">
      <section class="panel form-stack">
        <span class="status-pill">{{ statusLabel(text(detail.data.value, 'status')) }}</span>
        <h2>{{ text(detail.data.value, 'subject') }}</h2>
        <p class="description">{{ text(detail.data.value, 'body') }}</p>
        <p v-if="text(detail.data.value, 'reason')" class="notice">
          处理依据：{{ text(detail.data.value, 'reason') }}
        </p>
        <article
          v-for="message in children(detail.data.value, 'messages').filter(
            (item) => staff || !item.internal,
          )"
          :key="number(message, 'id')"
          class="timeline-entry"
        >
          <b>{{ text(message, 'nickname') }} {{ message.internal ? '· 内部备注' : '' }}</b>
          <p class="description">{{ text(message, 'body') }}</p>
          <small>{{ date(number(message, 'created')) }}</small>
        </article>
        <form class="form-stack" @submit.prevent="reply">
          <label
            >补充说明 / 回复<textarea
              v-model="form.body"
              required
              maxlength="3000"
              rows="4"
            /></label
          ><label v-if="staff" class="checkbox-line"
            ><input v-model="form.internal" type="checkbox" />仅内部备注，不发送给用户</label
          ><AppButton type="submit" :loading="action.busy.value">发送回复</AppButton>
        </form>
      </section>
      <aside class="form-stack">
        <section class="panel">
          <h2>关联信息</h2>
          <template v-if="order.data.value"
            ><RouterLink to="/orders">订单 #{{ number(order.data.value, 'id') }}</RouterLink>
            <p>
              {{ statusLabel(text(order.data.value, 'status')) }} · ¥{{
                money(number(order.data.value, 'total'))
              }}
            </p>
            <p>交付时间：{{ date(number(order.data.value, 'appointment')) }}</p></template
          >
          <p v-else class="muted">尚未关联订单，不能据此推断金额与交易责任。</p>
          <RouterLink
            v-if="number(detail.data.value, 'product_id')"
            :to="'/products/' + number(detail.data.value, 'product_id')"
            >查看涉事商品</RouterLink
          ><AppButton
            v-if="!staff && text(detail.data.value, 'status') !== 'resolved'"
            @click="contact"
            >联系在线客服</AppButton
          ><AppButton v-if="staff" variant="quiet" @click="loadCandidates">关联订单</AppButton>
          <form v-if="candidates.length" class="form-stack" @submit.prevent="linkOrder">
            <select v-model="form.link" required aria-label="选择关联订单">
              <option value="">请选择</option>
              <option
                v-for="candidate in candidates"
                :key="number(candidate, 'id')"
                :value="number(candidate, 'id')"
              >
                #{{ number(candidate, 'id') }} · ¥{{ money(number(candidate, 'total')) }}
              </option></select
            ><AppButton type="submit">确认关联</AppButton>
          </form>
        </section>
        <form
          v-if="staff && text(detail.data.value, 'status') !== 'resolved'"
          class="panel form-stack"
          @submit.prevent="resolve"
        >
          <h2>处理工单</h2>
          <p v-if="conflict" class="error-text">你与此工单存在利益冲突，不能处理。</p>
          <label
            >处理方式<select v-model="outcome" :disabled="conflict">
              <option value="claim">认领工单</option>
              <option value="review">提交复核</option>
              <option
                v-if="text(detail.data.value, 'type') === 'refund' && order.data.value"
                value="refund"
              >
                模拟退款
              </option>
              <option value="reject">不支持退款 / 结案</option>
              <option value="resolved">协商完成并结案</option>
            </select></label
          ><label v-if="outcome === 'refund'"
            >退款金额（元，不填为全额）<input v-model="form.amount" inputmode="decimal" /></label
          ><label
            >证据与处理依据<textarea
              v-model="form.reason"
              required
              maxlength="1000"
              rows="4"
            /></label
          ><AppButton type="submit" :loading="action.busy.value" :disabled="conflict"
            >确认处理</AppButton
          >
        </form>
      </aside>
    </div></LoadBoundary
  ><template v-else
    ><AssistantPanel v-if="localFaqEnabled" />
    <div class="panel tabs">
      <button
        v-for="status in ['', 'open', 'processing', 'review', 'resolved']"
        :key="status"
        :aria-pressed="filter === status"
        @click="filter = status"
      >
        {{ status ? statusLabel(status) : '全部工单' }}
      </button>
    </div>
    <LoadBoundary
      :loading="tickets.loading.value"
      :error="tickets.error.value"
      :empty="!!tickets.data.value && !visible.length"
      @retry="tickets.reload"
      ><div class="panel">
        <RouterLink
          v-for="ticket in visible"
          :key="number(ticket, 'id')"
          :to="'/support/' + number(ticket, 'id')"
          class="ticket-row"
          ><div>
            <b>{{ text(ticket, 'subject') }}</b>
            <p class="muted">
              #{{ number(ticket, 'id') }} · {{ text(ticket, 'nickname') }} ·
              {{ date(number(ticket, 'created')) }}
            </p>
          </div>
          <span class="status-pill">{{ statusLabel(text(ticket, 'status')) }}</span></RouterLink
        >
      </div></LoadBoundary
    >
    <section class="panel">
      <h2>信誉与申诉</h2>
      <p>初始 100 分，低于 60 分暂停发布。举报、点赞不会自动扣分，所有处罚须经核查并关联证据。</p>
      <p v-for="entry in history.data.value" :key="number(entry, 'id')">
        {{ number(entry, 'delta') > 0 ? '+' : '' }}{{ number(entry, 'delta') }} ·
        {{ text(entry, 'reason') }} · {{ date(number(entry, 'created')) }}
      </p>
      <RouterLink to="/support/new?type=appeal">提出申诉</RouterLink>
    </section></template
  >
</template>
