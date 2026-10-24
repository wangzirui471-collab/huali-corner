<script setup>
import { ref, computed } from 'vue';
import { RouterLink } from 'vue-router';

import { rows, text, number, money, statusLabel } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import AppButton from '@/shared/ui/AppButton.vue';
const filter = ref(''),
  action = useAction(),
  products = useLoad(async (signal) => rows(await api('/my-products', { signal })));
const visible = computed(() =>
  (products.data.value || []).filter(
    (item) => !filter.value || text(item, 'status') === filter.value,
  ),
);
/** 自有商品上下架仍由原服务检查归属、预留与平台处置状态。 @param {number} id 商品。 @param {string} operation 动作。 */
async function manage(id, operation) {
  await action.run(async () => {
    await api('/product/status', { body: { id, action: operation } });
    await products.reload();
  }, '商品状态已更新');
}
/** 推广是模拟交易，明确选择期限后才发请求。 @param {number} id 商品。 @param {string} tier 期限。 */
async function promote(id, tier) {
  if (!window.confirm('确认按 ' + tier + ' 期限进行模拟推广？费用和资格以服务端为准。')) return;
  await action.run(async () => {
    await api('/product/promote', { body: { id, tier } });
    await products.reload();
  }, '模拟推广已提交');
}
</script>
<template>
  <section>
    <header class="section-heading">
      <div>
        <span class="eyebrow">MY LISTINGS</span>
        <h1>我发布的</h1>
      </div>
      <RouterLink to="/publish">发布新闲置 ↗</RouterLink>
    </header>
    <TaskFeedback :error="action.error.value" :notice="action.notice.value" /><label
      class="filter-control"
      >商品状态<select v-model="filter">
        <option value="">全部</option>
        <option
          v-for="status in ['available', 'reserved', 'sold', 'removed']"
          :key="status"
          :value="status"
        >
          {{ statusLabel(status) }}
        </option>
      </select></label
    ><LoadBoundary
      :loading="products.loading.value"
      :error="products.error.value"
      :forbidden="products.forbidden.value"
      :empty="!!products.data.value && !visible.length"
      @retry="products.reload"
      ><article v-for="item in visible" :key="number(item, 'id')" class="panel listing-row">
        <div>
          <RouterLink :to="'/products/' + number(item, 'id')"
            ><h2>{{ text(item, 'title') }}</h2></RouterLink
          >
          <p>¥{{ money(number(item, 'price')) }} · {{ statusLabel(text(item, 'status')) }}</p>
          <p class="muted">{{ text(item, 'review_reason') || text(item, 'removed_reason') }}</p>
        </div>
        <div class="actions">
          <AppButton
            v-if="text(item, 'status') === 'available'"
            variant="secondary"
            :loading="action.busy.value"
            @click="manage(number(item, 'id'), 'delist')"
            >下架</AppButton
          ><AppButton
            v-if="text(item, 'status') === 'removed'"
            variant="secondary"
            :loading="action.busy.value"
            @click="manage(number(item, 'id'), 'relist')"
            >申请重新上架</AppButton
          ><template v-if="text(item, 'status') === 'available'"
            ><AppButton
              v-for="tier in ['1d', '3d', '7d']"
              :key="tier"
              variant="quiet"
              :disabled="action.busy.value"
              @click="promote(number(item, 'id'), tier)"
              >推广 {{ tier }}</AppButton
            ></template
          >
        </div>
      </article></LoadBoundary
    >
  </section>
</template>
