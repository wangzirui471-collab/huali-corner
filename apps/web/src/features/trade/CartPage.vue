<script setup>
import { computed, reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { session, changeCart, readStorage, writeStorage } from '@/shared/legacy/session.js';
import { row, number, text, money, children } from '@/shared/legacy/dto.js';
import { ApiError } from '@/shared/http/client.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import AppButton from '@/shared/ui/AppButton.vue';
import AuthenticatedImage from '@/shared/ui/AuthenticatedImage.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import { createCheckoutAttempt } from './checkout.js';
const router = useRouter(),
  action = useAction(),
  buyer = number(session.me, 'id'),
  recoveryKey = `hc-vue-checkout-${buyer}`;
/** 仅恢复本账号的上一次请求，不生成新键掩盖未知结果。 */
function restoreAttempt() {
  try {
    const saved = row(JSON.parse(readStorage(recoveryKey, true) || '{}'));
    const snapshot = row(saved.snapshot);
    if (typeof snapshot.key !== 'string' || typeof snapshot.fingerprint !== 'string') return null;
    return {
      snapshot: { key: snapshot.key, fingerprint: snapshot.fingerprint },
      body: row(saved.body),
    };
  } catch {
    return null;
  }
}
const restored = restoreAttempt(),
  attempt = createCheckoutAttempt(restored?.snapshot || null),
  uncertain = ref(!!restored);
const form = reactive({
  delivery: text(restored?.body, 'delivery', 'pickup'),
  address: text(restored?.body, 'address'),
  appointment: restored?.body.appointment
    ? new Date(number(restored.body, 'appointment') * 1000 - new Date().getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16)
    : '',
});
const products = useLoad(async (signal) =>
  Promise.all(session.cart.map(async (id) => row(await api('/product?id=' + id, { signal })))),
);
const selected = computed(() =>
  (products.data.value || []).filter((product) => session.cart.includes(number(product, 'id'))),
);
const sellerCount = computed(
  () => new Set(selected.value.map((product) => number(product, 'seller_id'))).size,
);
const total = computed(() =>
  selected.value.reduce((sum, product) => sum + number(product, 'price'), 0),
);
const deliveryFee = computed(() =>
  form.delivery === 'delivery'
    ? Math.max(0, ...selected.value.map((product) => number(product, 'delivery_fee')))
    : 0,
);
/** 明确成功后清理清单；异常时保留内容与幂等快照供原键恢复。 */
async function checkout() {
  await action.run(async () => {
    if (!selected.value.length || sellerCount.value !== 1)
      throw new Error('请选择同一卖家的 1–20 件商品');
    if (selected.value.some((product) => number(product, 'seller_id') === buyer))
      throw new Error('不能购买自己的商品');
    const appointment = new Date(form.appointment).getTime() / 1000;
    if (!Number.isFinite(appointment)) throw new Error('请选择交付时间');
    const body = /** @type {import('./checkout.js').CheckoutBody} */ ({
      product_ids: selected.value.map((product) => number(product, 'id')),
      delivery: form.delivery,
      address: form.address,
      appointment,
    });
    try {
      const want = row(JSON.parse(readStorage(`hc-vue-want-${buyer}`, true) || '{}'));
      if (body.product_ids.includes(number(want, 'product'))) body.want_id = number(want, 'want');
    } catch {
      /* 无撮合来源时按普通订单提交。 */
    }
    const payload = attempt.prepare(buyer, body);
    if (!writeStorage(recoveryKey, JSON.stringify({ snapshot: attempt.snapshot(), body }), true))
      throw new Error('浏览器无法保存下单恢复信息，请允许会话存储后重试');
    try {
      await api('/checkout', { body: payload });
      attempt.clear();
      writeStorage(recoveryKey, null, true);
      writeStorage(`hc-vue-want-${buyer}`, null, true);
      for (const id of [...session.cart]) changeCart(id, false);
      await router.push('/orders');
    } catch (error) {
      if (error instanceof ApiError && !error.outcomeUnknown) {
        attempt.clear();
        writeStorage(recoveryKey, null, true);
        uncertain.value = false;
      } else uncertain.value = true;
      throw error;
    }
  }, '模拟订单已生成');
}
</script>
<template>
  <header class="section-heading">
    <div>
      <span class="eyebrow">PICKUP TOGETHER</span>
      <h1>取货清单</h1>
      <p class="muted">同卖家多件合并取货；付款、退款与结算均为模拟。</p>
    </div>
    <RouterLink to="/orders">查看订单</RouterLink>
  </header>
  <TaskFeedback :error="action.error.value" />
  <div v-if="uncertain" class="notice">
    上一次下单结果待确认。请先查看订单；原内容重试会沿用原键，不会主动换键生成第二张单。
  </div>
  <LoadBoundary
    :loading="products.loading.value"
    :error="products.error.value"
    :empty="!!products.data.value && !selected.length"
    @retry="products.reload"
    ><div class="checkout-layout">
      <section class="panel">
        <article v-for="product in selected" :key="number(product, 'id')" class="list-row">
          <div class="small-cover">
            <AuthenticatedImage
              :src="text(children(product, 'photos')[0], 'url')"
              :alt="text(product, 'title')"
            />
          </div>
          <div>
            <RouterLink :to="'/products/' + number(product, 'id')">{{
              text(product, 'title')
            }}</RouterLink>
            <p class="muted">{{ text(product, 'nickname') }} · {{ text(product, 'region') }}</p>
            <b>¥{{ money(number(product, 'price')) }}</b>
          </div>
          <AppButton
            variant="quiet"
            :disabled="uncertain"
            @click="changeCart(number(product, 'id'), false)"
            >移除</AppButton
          >
        </article>
      </section>
      <form class="panel form-stack" @submit.prevent="checkout">
        <h2>约定交付</h2>
        <p v-if="sellerCount > 1" class="error-text">清单含不同卖家，请分别下单。</p>
        <label
          >交付方式<select v-model="form.delivery" :disabled="uncertain">
            <option value="pickup">自提</option>
            <option value="delivery">卖家送货</option>
          </select></label
        ><label
          >公共交付地点<input
            v-model="form.address"
            maxlength="150"
            :required="form.delivery === 'delivery'"
            :disabled="uncertain" /></label
        ><label
          >约定时间<input
            v-model="form.appointment"
            type="datetime-local"
            required
            :disabled="uncertain"
        /></label>
        <dl class="summary">
          <dt>商品小计</dt>
          <dd>¥{{ money(total) }}</dd>
          <dt>送货费</dt>
          <dd>¥{{ money(deliveryFee) }}</dd>
          <dt>合计</dt>
          <dd>
            <b>¥{{ money(total + deliveryFee) }}</b>
          </dd>
        </dl>
        <p class="muted">最终价格以服务器核对的商品和已接受报价为准。</p>
        <AppButton type="submit" :loading="action.busy.value" :disabled="sellerCount !== 1">{{
          uncertain ? '按原请求恢复结果' : '生成模拟订单'
        }}</AppButton>
      </form>
    </div></LoadBoundary
  >
</template>
