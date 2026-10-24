<script setup>
import { computed, reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { session } from '@/shared/legacy/session.js';
import { rows, children, text, number, money, date, statusLabel } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import { orderActions } from './checkout.js';
const router = useRouter(),
  action = useAction(),
  role = ref(''),
  filter = ref(''),
  selected = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null)),
  operation = ref('');
const form = reactive({
  appointment: '',
  address: '',
  delivery: 'pickup',
  rating: '5',
  body: '',
  keep: /** @type {number[]} */ ([]),
});
const orderList = useLoad(async (signal) => rows(await api('/orders', { signal })));
const offers = useLoad(async (signal) => rows(await api('/offers', { signal })));
const groups = [
  { key: '', label: '全部状态', states: /** @type {string[]} */ ([]) },
  { key: 'awaiting_payment', label: '待付款', states: ['awaiting_payment'] },
  {
    key: 'receiving',
    label: '待交付 / 收货',
    states: ['paid', 'awaiting_handover', 'awaiting_receipt'],
  },
  { key: 'after', label: '售后', states: ['disputed', 'refunded', 'partial_refunded'] },
  { key: 'completed', label: '已完成', states: ['completed'] },
  { key: 'cancelled', label: '已取消', states: ['cancelled'] },
];
const visible = computed(() =>
  (orderList.data.value || []).filter(
    (order) =>
      (!role.value ||
        number(order, role.value === 'buy' ? 'buyer_id' : 'seller_id') ===
          number(session.me, 'id')) &&
      (!filter.value ||
        groups.find((group) => group.key === filter.value)?.states.includes(text(order, 'status'))),
  ),
);
const labels = /** @type {Record<string,string>} */ ({
  pay: '模拟付款',
  cancel: '取消订单',
  edit: '付款前修改',
  confirm_schedule: '确认交付时间',
  deliver: '标记已交付',
  handover: '核对交接',
  receive: '确认收货',
  refund: '申请售后',
  reschedule: '申请改约',
  review: '评价订单',
});
/** 显示动作依据来自旧接口状态，所有提交仍由原后端最终校验。 @param {import('@/shared/legacy/dto.js').Row} order 订单。 */
function actions(order) {
  return orderActions(
    {
      buyer_id: number(order, 'buyer_id'),
      seller_id: number(order, 'seller_id'),
      status: text(order, 'status'),
      schedule_confirmed: !!order.schedule_confirmed,
    },
    number(session.me, 'id'),
  );
}
/** 打开明确的后果确认与原值编辑；取消不发送任何请求。 @param {import('@/shared/legacy/dto.js').Row} order 订单。 @param {string} kind 动作。 */
function open(order, kind) {
  if (kind === 'refund') {
    void router.push({
      path: '/support/new',
      query: { type: 'refund', order: number(order, 'id') },
    });
    return;
  }
  selected.value = order;
  operation.value = kind;
  form.appointment = new Date(
    number(order, 'appointment') * 1000 - new Date().getTimezoneOffset() * 60000,
  )
    .toISOString()
    .slice(0, 16);
  form.address = text(order, 'address');
  form.delivery = text(order, 'delivery', 'pickup');
  form.keep = children(order, 'items').map((item) => number(item, 'id'));
  form.body = '';
}
/** 付款前卖家只提交时间，买家可调整商品；改约与评价沿用原接口。 */
async function submit() {
  if (!selected.value) return;
  const order = selected.value,
    id = number(order, 'id'),
    kind = operation.value;
  await action.run(async () => {
    if (kind === 'edit') {
      const payload = /** @type {Record<string,unknown>} */ ({
        id,
        appointment: new Date(form.appointment).getTime() / 1000,
      });
      if (number(order, 'buyer_id') === number(session.me, 'id'))
        Object.assign(payload, {
          product_ids: form.keep,
          delivery: form.delivery,
          address: form.address,
        });
      await api('/order/update', { body: payload });
    } else if (kind === 'review')
      await api('/review', {
        body: { order_id: id, rating: Number(form.rating), body: form.body },
      });
    else
      await api('/order/action', {
        body: {
          id,
          action: kind,
          ...(kind === 'reschedule'
            ? { appointment: new Date(form.appointment).getTime() / 1000, address: form.address }
            : {}),
        },
      });
    selected.value = null;
    await orderList.reload();
  }, '订单操作已记录 · 当前为模拟交易');
}
/** 处理待确认改约，不重新拼造订单金额。 @param {number} id 改约编号。 @param {boolean} accept 是否接受。 */
async function respond(id, accept) {
  await action.run(async () => {
    await api('/order/change', { body: { id, accept } });
    await orderList.reload();
  }, '改约已处理');
}
/** 卖家接受或拒绝报价，结果在刷新订单后展示。 @param {number} id 报价编号。 @param {boolean} accept 是否接受。 */
async function decideOffer(id, accept) {
  await action.run(async () => {
    await api('/offer/accept', { body: { id, accept } });
    await offers.reload();
  }, '报价已处理');
}
</script>
<template>
  <header class="section-heading">
    <div>
      <span class="eyebrow">EVERY STEP MATTERS</span>
      <h1>我的订单</h1>
      <p class="muted">订单、付款、退款和结算均为模拟。</p>
    </div>
    <RouterLink to="/cart">取货清单</RouterLink>
  </header>
  <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
  <div class="panel tabs">
    <button
      v-for="tab in [
        { key: '', label: '全部' },
        { key: 'buy', label: '我买到的' },
        { key: 'sell', label: '我卖出的' },
      ]"
      :key="tab.key"
      :aria-pressed="role === tab.key"
      @click="role = tab.key"
    >
      {{ tab.label }}</button
    ><select v-model="filter" aria-label="订单状态">
      <option v-for="group in groups" :key="group.key" :value="group.key">{{ group.label }}</option>
    </select>
  </div>
  <section v-if="offers.error.value" class="notice">
    报价读取失败：{{ offers.error.value }} <button @click="offers.reload">重试</button>
  </section>
  <section v-if="offers.data.value?.length" class="panel">
    <h2>出价记录</h2>
    <div v-for="offer in offers.data.value" :key="number(offer, 'id')" class="list-row">
      <span
        >{{ text(offer, 'title') }} · ¥{{ money(number(offer, 'amount')) }} ·
        {{ statusLabel(text(offer, 'status')) }}</span
      ><template
        v-if="
          number(offer, 'seller_id') === number(session.me, 'id') &&
          text(offer, 'status') === 'pending'
        "
        ><AppButton variant="secondary" @click="decideOffer(number(offer, 'id'), true)"
          >接受</AppButton
        ><AppButton variant="quiet" @click="decideOffer(number(offer, 'id'), false)"
          >拒绝</AppButton
        ></template
      >
    </div>
  </section>
  <LoadBoundary
    :loading="orderList.loading.value"
    :error="orderList.error.value"
    :empty="!!orderList.data.value && !visible.length"
    @retry="orderList.reload"
    ><div class="form-stack">
      <article v-for="order in visible" :key="number(order, 'id')" class="panel">
        <header class="section-heading">
          <h2>
            订单 #{{ number(order, 'id') }} ·
            {{ number(order, 'buyer_id') === number(session.me, 'id') ? '我买到的' : '我卖出的' }}
          </h2>
          <span class="status-pill">{{ statusLabel(text(order, 'status')) }}</span>
        </header>
        <div v-for="item in children(order, 'items')" :key="number(item, 'id')" class="list-row">
          <div>
            <RouterLink :to="'/products/' + number(item, 'id')">{{
              text(item, 'title')
            }}</RouterLink>
            <p class="muted">
              {{
                ['edition', 'notes', 'missing', 'accessories']
                  .map((key) => text(item, key))
                  .filter(Boolean)
                  .join(' · ')
              }}
            </p>
          </div>
          <b>¥{{ money(number(item, 'price')) }}</b>
        </div>
        <p>
          {{ text(order, 'delivery') === 'pickup' ? '自提' : '卖家送货' }} ·
          {{ text(order, 'address') }} · {{ date(number(order, 'appointment')) }}
        </p>
        <p>
          <b>合计 ¥{{ money(number(order, 'total')) }}</b
          >（送货 ¥{{ money(number(order, 'delivery_fee')) }}）
        </p>
        <div v-if="text(order, 'status') === 'awaiting_receipt'" class="notice">
          交接后24小时自动收货：{{
            date(number(order, 'handover_at') + 86400)
          }}。有异议请及时申请售后。
        </div>
        <details>
          <summary>模拟账本与订单说明</summary>
          <p v-for="entry in children(order, 'ledger')" :key="number(entry, 'id')">
            {{ text(entry, 'kind') }} · ¥{{ money(number(entry, 'amount')) }} ·
            {{ date(number(entry, 'created')) }}
          </p>
          <p v-for="note in children(order, 'notes')" :key="number(note, 'id')">
            {{ text(note, 'body') }}
          </p>
        </details>
        <div class="actions">
          <AppButton
            v-for="kind in actions(order)"
            :key="kind"
            :variant="kind === 'pay' ? 'primary' : 'secondary'"
            :disabled="action.busy.value"
            @click="open(order, kind)"
            >{{ labels[kind] }}</AppButton
          >
        </div>
        <div
          v-for="change in children(order, 'changes').filter(
            (item) => text(item, 'status') === 'pending',
          )"
          :key="number(change, 'id')"
          class="notice"
        >
          待确认改约：{{ date(number(change, 'appointment')) }} · {{ text(change, 'address') }}
          <div v-if="number(change, 'proposer') !== number(session.me, 'id')" class="actions">
            <AppButton variant="secondary" @click="respond(number(change, 'id'), true)"
              >接受</AppButton
            ><AppButton variant="quiet" @click="respond(number(change, 'id'), false)"
              >拒绝</AppButton
            >
          </div>
        </div>
      </article>
    </div></LoadBoundary
  ><AppDialog
    :open="!!selected"
    :title="labels[operation] || '订单操作'"
    @close="!action.busy.value && (selected = null)"
    ><form class="form-stack" @submit.prevent="submit">
      <p>
        订单 #{{ number(selected, 'id') }} ·
        {{ labels[operation] }}。请核对实物与约定，当前资金均为模拟。
      </p>
      <template v-if="['edit', 'reschedule'].includes(operation)"
        ><label>交付时间<input v-model="form.appointment" type="datetime-local" required /></label
        ><template
          v-if="
            operation === 'reschedule' || number(selected, 'buyer_id') === number(session.me, 'id')
          "
          ><label>公共交付地点<input v-model="form.address" maxlength="150" /></label
          ><template v-if="operation === 'edit'"
            ><label
              >交付方式<select v-model="form.delivery">
                <option value="pickup">自提</option>
                <option value="delivery">卖家送货</option>
              </select></label
            ><label
              v-for="item in children(selected, 'items')"
              :key="number(item, 'id')"
              class="checkbox-line"
              ><input v-model="form.keep" type="checkbox" :value="number(item, 'id')" />保留
              {{ text(item, 'title') }}</label
            ></template
          ></template
        ></template
      ><template v-if="operation === 'review'"
        ><label
          >评分<select v-model="form.rating">
            <option v-for="rating in [5, 4, 3, 2, 1]" :key="rating">{{ rating }}</option>
          </select></label
        ><label>评价<textarea v-model="form.body" required maxlength="1000" /></label></template
      ><TaskFeedback :error="action.error.value" /><AppButton
        type="submit"
        :loading="action.busy.value"
        >确认{{ labels[operation] }}</AppButton
      >
    </form></AppDialog
  >
</template>
