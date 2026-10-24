<script setup>
import { computed, reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { session } from "@/shared/legacy/session.js";
import {
  rows,
  children,
  text,
  number,
  money,
  date,
  statusLabel,
} from "@/shared/legacy/dto.js";
import { useLoad, useAction } from "@/shared/legacy/use-task.js";
import { useLegacyApi } from "@/shared/legacy/use-task.js";
const api = useLegacyApi();
import AppButton from "@/shared/ui/AppButton.vue";
import AppDialog from "@/shared/ui/AppDialog.vue";
import LoadBoundary from "@/shared/ui/LoadBoundary.vue";
import TaskFeedback from "@/shared/ui/TaskFeedback.vue";
import { orderActions } from "@/features/trade/checkout.js";
import AppIcon from "@/shared/ui/AppIcon.vue";
const router = useRouter(),
  action = useAction(),
  role = ref(""),
  filter = ref(""),
  selected = ref(
    /** @type {import('@/shared/legacy/dto.js').Row|null} */ (null),
  ),
  operation = ref("");
const form = reactive({
  appointment: "",
  address: "",
  delivery: "pickup",
  rating: "5",
  body: "",
  keep: /** @type {number[]} */ ([]),
});
const orderList = useLoad(async (signal) =>
  rows(await api("/orders", { signal })),
);
const offers = useLoad(async (signal) =>
  rows(await api("/offers", { signal })),
);
const groups = [
  { key: "", label: "全部状态", states: /** @type {string[]} */ ([]) },
  { key: "awaiting_payment", label: "待付款", states: ["awaiting_payment"] },
  {
    key: "receiving",
    label: "待交付 / 收货",
    states: ["paid", "awaiting_handover", "awaiting_receipt"],
  },
  {
    key: "after",
    label: "售后",
    states: ["disputed", "refunded", "partial_refunded"],
  },
  { key: "completed", label: "已完成", states: ["completed"] },
  { key: "cancelled", label: "已取消", states: ["cancelled"] },
];
const visible = computed(() =>
  (orderList.data.value || []).filter(
    (order) =>
      (!role.value ||
        number(order, role.value === "buy" ? "buyer_id" : "seller_id") ===
          number(session.me, "id")) &&
      (!filter.value ||
        groups
          .find((group) => group.key === filter.value)
          ?.states.includes(text(order, "status"))),
  ),
);
const labels = /** @type {Record<string,string>} */ ({
  pay: "模拟付款",
  cancel: "取消订单",
  edit: "付款前修改",
  confirm_schedule: "确认交付时间",
  deliver: "标记已交付",
  handover: "核对交接",
  receive: "确认收货",
  refund: "申请售后",
  reschedule: "申请改约",
  review: "评价订单",
});
/** 状态数量随买卖归属一起筛选，不把另一身份的订单混入计数。 @param {{key: string, states: string[]}} group 状态组。 */
function countOrders(group) {
  return (orderList.data.value || []).filter(
    (order) =>
      (!role.value ||
        number(order, role.value === "buy" ? "buyer_id" : "seller_id") ===
          number(session.me, "id")) &&
      (!group.key || group.states.includes(text(order, "status"))),
  ).length;
}
/** 显示动作依据来自旧接口状态，所有提交仍由原后端最终校验。 @param {import('@/shared/legacy/dto.js').Row} order 订单。 */
function actions(order) {
  return orderActions(
    {
      buyer_id: number(order, "buyer_id"),
      seller_id: number(order, "seller_id"),
      status: text(order, "status"),
      schedule_confirmed: !!order.schedule_confirmed,
    },
    number(session.me, "id"),
  );
}
/** 打开明确的后果确认与原值编辑；取消不发送任何请求。 @param {import('@/shared/legacy/dto.js').Row} order 订单。 @param {string} kind 动作。 */
function open(order, kind) {
  if (kind === "refund") {
    void router.push({
      path: "/support/new",
      query: { type: "refund", order: number(order, "id") },
    });
    return;
  }
  selected.value = order;
  operation.value = kind;
  form.appointment = new Date(
    number(order, "appointment") * 1000 -
      new Date().getTimezoneOffset() * 60000,
  )
    .toISOString()
    .slice(0, 16);
  form.address = text(order, "address");
  form.delivery = text(order, "delivery", "pickup");
  form.keep = children(order, "items").map((item) => number(item, "id"));
  form.body = "";
}
/** 付款前卖家只提交时间，买家可调整商品；改约与评价沿用原接口。 */
async function submit() {
  if (!selected.value) return;
  const order = selected.value,
    id = number(order, "id"),
    kind = operation.value;
  await action.run(async () => {
    if (kind === "edit") {
      const payload = /** @type {Record<string,unknown>} */ ({
        id,
        appointment: new Date(form.appointment).getTime() / 1000,
      });
      if (number(order, "buyer_id") === number(session.me, "id"))
        Object.assign(payload, {
          product_ids: form.keep,
          delivery: form.delivery,
          address: form.address,
        });
      await api("/order/update", { body: payload });
    } else if (kind === "review")
      await api("/review", {
        body: { order_id: id, rating: Number(form.rating), body: form.body },
      });
    else
      await api("/order/action", {
        body: {
          id,
          action: kind,
          ...(kind === "reschedule"
            ? {
                appointment: new Date(form.appointment).getTime() / 1000,
                address: form.address,
              }
            : {}),
        },
      });
    selected.value = null;
    await orderList.reload();
  }, "订单操作已记录 · 当前为模拟交易");
}
/** 处理待确认改约，不重新拼造订单金额。 @param {number} id 改约编号。 @param {boolean} accept 是否接受。 */
async function respond(id, accept) {
  await action.run(async () => {
    await api("/order/change", { body: { id, accept } });
    await orderList.reload();
  }, "改约已处理");
}
/** 卖家接受或拒绝报价，结果在刷新订单后展示。 @param {number} id 报价编号。 @param {boolean} accept 是否接受。 */
async function decideOffer(id, accept) {
  await action.run(async () => {
    await api("/offer/accept", { body: { id, accept } });
    await offers.reload();
  }, "报价已处理");
}
</script>
<template>
  <section class="orders-review">
    <header class="orders-title">
      <div>
        <span class="review-kicker">MY EXCHANGES</span>
        <h1>每一次转交，都有着落。</h1>
        <p>我的订单 <span>／ 买到的与卖出的，都在这里。</span></p>
      </div>
      <RouterLink to="/cart" class="text-action"
        ><AppIcon name="bag" :size="18" />取货清单 →</RouterLink
      >
    </header>
    <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
    <div class="orders-columns">
      <aside class="order-filters">
        <span class="review-kicker">订单状态</span>
        <nav aria-label="订单状态">
          <button
            v-for="group in groups"
            :key="group.key"
            :data-order-filter="group.key"
            :aria-pressed="filter === group.key"
            @click="filter = group.key"
          >
            <span>{{ group.label }}</span
            ><b>{{ countOrders(group) }}</b>
          </button>
        </nav>
        <p class="order-simulation">
          <AppIcon
            name="help"
            :size="18"
          />当前为模拟交易<br />不会扣取真实款项。
        </p>
        <RouterLink to="/support">需要帮助与售后？ →</RouterLink>
      </aside>
      <div class="orders-content">
        <div class="order-role" aria-label="订单归属">
          <button
            v-for="tab in [
              { key: '', label: '全部订单' },
              { key: 'buy', label: '我买到的' },
              { key: 'sell', label: '我卖出的' },
            ]"
            :key="tab.key"
            :aria-pressed="role === tab.key"
            @click="role = tab.key"
          >
            {{ tab.label }}</button
          ><span>{{ visible.length }} 笔订单</span>
        </div>
        <LoadBoundary
          :loading="orderList.loading.value"
          :error="orderList.error.value"
          :empty="!!orderList.data.value && !visible.length"
          @retry="orderList.reload"
        >
          <div class="order-paper">
            <article
              v-for="order in visible"
              :key="number(order, 'id')"
              class="review-order"
              :data-state="text(order, 'status')"
            >
              <header class="order-top">
                <div>
                  <span class="order-status"
                    ><i aria-hidden="true" />{{
                      statusLabel(text(order, "status"))
                    }}</span
                  ><span class="order-side">{{
                    number(order, "buyer_id") === number(session.me, "id")
                      ? "我买到的"
                      : "我卖出的"
                  }}</span>
                </div>
                <span class="order-number"
                  >订单 #{{ number(order, "id") }}</span
                >
              </header>
              <div class="order-items">
                <div
                  v-for="item in children(order, 'items')"
                  :key="number(item, 'id')"
                  class="order-item"
                >
                  <span class="order-item-symbol" aria-hidden="true"
                    ><AppIcon name="bag" :size="28"
                  /></span>
                  <div>
                    <RouterLink :to="'/products/' + number(item, 'id')"
                      ><h2>{{ text(item, "title") }}</h2></RouterLink
                    >
                    <p>
                      {{
                        ["edition", "notes", "missing", "accessories"]
                          .map((key) => text(item, key))
                          .filter(Boolean)
                          .join(" · ") || "商品状态以订单快照及双方核对为准"
                      }}
                    </p>
                  </div>
                  <b>¥{{ money(number(item, "price")) }}</b>
                </div>
              </div>
              <div class="delivery-line">
                <span
                  ><AppIcon name="pin" :size="16" />{{
                    text(order, "address") || "交付地点以约定为准"
                  }}</span
                ><span
                  ><AppIcon name="clock" :size="16" />{{
                    date(number(order, "appointment"))
                  }}</span
                ><span>{{
                  text(order, "delivery") === "pickup" ? "当面自提" : "卖家送货"
                }}</span>
              </div>
              <div
                v-if="text(order, 'status') === 'awaiting_payment'"
                class="order-next"
              >
                <b>下一步 · 等待买家模拟付款</b
                ><span>先核对商品与交付约定，再继续。</span>
              </div>
              <div
                v-else-if="text(order, 'status') === 'awaiting_receipt'"
                class="order-next"
              >
                <b>下一步 · 等待买家确认收货</b
                ><span
                  >交接后 24 小时自动收货：{{
                    date(number(order, "handover_at") + 86400)
                  }}。有异议请及时申请售后。</span
                >
              </div>
              <div
                v-else-if="text(order, 'status') === 'completed'"
                class="order-complete"
              >
                <AppIcon
                  name="gift"
                  :size="18"
                />这次转交已完成，感谢让好物继续被使用。
              </div>
              <footer class="order-bottom">
                <div class="order-total">
                  <small>合计</small><b>¥{{ money(number(order, "total")) }}</b
                  ><span
                    >含送货 ¥{{ money(number(order, "delivery_fee")) }}</span
                  >
                </div>
                <div class="actions">
                  <AppButton
                    v-for="kind in actions(order)"
                    :key="kind"
                    :variant="
                      [
                        'pay',
                        'receive',
                        'deliver',
                        'handover',
                        'confirm_schedule',
                      ].includes(kind)
                        ? 'primary'
                        : 'quiet'
                    "
                    :disabled="action.busy.value"
                    @click="open(order, kind)"
                    >{{ labels[kind] }}</AppButton
                  >
                </div>
              </footer>
              <details class="order-ledger">
                <summary>账本与订单说明</summary>
                <p
                  v-for="entry in children(order, 'ledger')"
                  :key="number(entry, 'id')"
                >
                  {{ text(entry, "kind") }} · ¥{{
                    money(number(entry, "amount"))
                  }}
                  · {{ date(number(entry, "created")) }}
                </p>
                <p
                  v-for="note in children(order, 'notes')"
                  :key="number(note, 'id')"
                >
                  {{ text(note, "body") }}
                </p>
              </details>
              <div
                v-for="change in children(order, 'changes').filter(
                  (item) => text(item, 'status') === 'pending',
                )"
                :key="number(change, 'id')"
                class="notice"
              >
                待确认改约：{{ date(number(change, "appointment")) }} ·
                {{ text(change, "address") }}
                <div
                  v-if="number(change, 'proposer') !== number(session.me, 'id')"
                  class="actions"
                >
                  <AppButton
                    variant="secondary"
                    @click="respond(number(change, 'id'), true)"
                    >接受</AppButton
                  ><AppButton
                    variant="quiet"
                    @click="respond(number(change, 'id'), false)"
                    >拒绝</AppButton
                  >
                </div>
              </div>
            </article>
          </div>
        </LoadBoundary>
        <section v-if="offers.error.value" class="notice">
          报价读取失败：{{ offers.error.value }}
          <button @click="offers.reload">重试</button>
        </section>
        <details v-if="offers.data.value?.length" class="offer-records">
          <summary>
            我的出价记录 <span>{{ offers.data.value.length }} 条</span>
          </summary>
          <div
            v-for="offer in offers.data.value"
            :key="number(offer, 'id')"
            class="list-row"
          >
            <span
              >{{ text(offer, "title") }} · ¥{{
                money(number(offer, "amount"))
              }}
              · {{ statusLabel(text(offer, "status")) }}</span
            ><template
              v-if="
                number(offer, 'seller_id') === number(session.me, 'id') &&
                text(offer, 'status') === 'pending'
              "
              ><AppButton
                variant="secondary"
                @click="decideOffer(number(offer, 'id'), true)"
                >接受</AppButton
              ><AppButton
                variant="quiet"
                @click="decideOffer(number(offer, 'id'), false)"
                >拒绝</AppButton
              ></template
            >
          </div>
        </details>
      </div>
    </div>
  </section>
  <AppDialog
    :open="!!selected"
    :title="labels[operation] || '订单操作'"
    @close="!action.busy.value && (selected = null)"
    ><form class="form-stack" @submit.prevent="submit">
      <p>
        订单 #{{ number(selected, "id") }} ·
        {{ labels[operation] }}。请核对实物与约定，当前资金均为模拟。
      </p>
      <template v-if="['edit', 'reschedule'].includes(operation)"
        ><label
          >交付时间<input
            v-model="form.appointment"
            type="datetime-local"
            required /></label
        ><template
          v-if="
            operation === 'reschedule' ||
            number(selected, 'buyer_id') === number(session.me, 'id')
          "
          ><label
            >公共交付地点<input v-model="form.address" maxlength="150" /></label
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
              ><input
                v-model="form.keep"
                type="checkbox"
                :value="number(item, 'id')"
              />保留 {{ text(item, "title") }}</label
            ></template
          ></template
        ></template
      ><template v-if="operation === 'review'"
        ><label
          >评分<select v-model="form.rating">
            <option v-for="rating in [5, 4, 3, 2, 1]" :key="rating">
              {{ rating }}
            </option>
          </select></label
        ><label
          >评价<textarea
            v-model="form.body"
            required
            maxlength="1000"
          /></label></template
      ><TaskFeedback :error="action.error.value" /><AppButton
        type="submit"
        :loading="action.busy.value"
        >确认{{ labels[operation] }}</AppButton
      >
    </form></AppDialog
  >
</template>
