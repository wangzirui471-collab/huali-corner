<script setup>
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, changeCart } from '@/shared/legacy/session.js';
import { row, rows, text, number, children, money, statusLabel } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import AppButton from '@/shared/ui/AppButton.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import AuthenticatedImage from '@/shared/ui/AuthenticatedImage.vue';
import ProductCard from './ProductCard.vue';
import { yuanToCents } from '@/features/trade/checkout.js';
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  selected = ref(0),
  offer = ref('');
const listing = useLoad(async (signal) =>
  row(await api('/product?id=' + route.params.id, { signal })),
);
const recommendations = useLoad(async (signal) =>
  rows(await api('/products?limit=5&page=1', { signal }))
    .filter((entry) => number(entry, 'id') !== Number(route.params.id))
    .slice(0, 4),
);
const own = computed(() => number(listing.data.value, 'seller_id') === number(session.me, 'id'));
const photos = computed(() => children(listing.data.value, 'photos'));
/** 买家加入清单；未登录时保留目标地址，服务端继续核验商品状态。 @param {boolean} [checkout] 是否立即结算。 */
async function add(checkout = false) {
  if (!session.me) {
    await router.push({ path: '/login', query: { next: route.fullPath } });
    return;
  }
  await action.run(async () => {
    changeCart(Number(route.params.id));
    if (checkout) await router.push('/cart');
  }, '已加入取货清单');
}
/** 收藏切换以服务器明确成功为准，不以乐观状态伪造结果。 */
async function favorite() {
  if (!session.me) {
    await router.push('/login');
    return;
  }
  await action.run(async () => {
    await api('/react', {
      body: {
        product_id: Number(route.params.id),
        kind: 'favorite',
        on: !listing.data.value?.favorited,
      },
    });
    await listing.reload();
  }, '收藏已更新');
}
/** 出价以整数分提交；接受结果在订单页核对。 */
async function submitOffer() {
  await action.run(async () => {
    await api('/offer', {
      body: { product_id: Number(route.params.id), amount: yuanToCents(offer.value) },
    });
    offer.value = '';
  }, '出价已提交，请在订单页查看结果');
}
/** 私聊仍受服务端好友前置与拉黑规则限制。 */
async function chat() {
  await action.run(async () => {
    const room = row(
      await api('/rooms/private', { body: { peer: number(listing.data.value, 'seller_id') } }),
    );
    await router.push('/messages/' + number(room, 'id'));
  });
}
/** 卖家管理只在本人详情出现，不向公共列表散落管理按钮。 @param {string} operation 上下架动作。 */
async function manage(operation) {
  await action.run(async () => {
    await api('/product/status', { body: { id: Number(route.params.id), action: operation } });
    await listing.reload();
  }, '商品状态已更新');
}
</script>
<template>
  <LoadBoundary
    :loading="listing.loading.value"
    :error="listing.error.value"
    :forbidden="listing.forbidden.value"
    @retry="listing.reload"
    ><template v-if="listing.data.value"
      ><nav class="breadcrumbs"><RouterLink to="/">逛逛</RouterLink> / 商品详情</nav>
      <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
      <div class="detail-layout">
        <section>
          <div class="detail-photo">
            <AuthenticatedImage
              :src="text(photos[selected], 'url')"
              :alt="text(listing.data.value, 'title')"
            />
          </div>
          <div class="photo-thumbs">
            <button
              v-for="(photo, index) in photos"
              :key="index"
              :aria-pressed="selected === index"
              :aria-label="'查看第' + (index + 1) + '张照片'"
              @click="selected = index"
            >
              <AuthenticatedImage :src="text(photo, 'url')" alt="商品缩略图" />
            </button>
          </div>
          <p v-if="listing.data.value.simulation" class="muted">示例商品与配图，仅用于模拟体验。</p>
        </section>
        <section class="panel detail-copy">
          <span class="eyebrow">{{ statusLabel(text(listing.data.value, 'status')) }}</span>
          <h1>{{ text(listing.data.value, 'title') }}</h1>
          <div class="detail-price">¥{{ money(number(listing.data.value, 'price')) }}</div>
          <p class="description">{{ text(listing.data.value, 'description') }}</p>
          <dl class="detail-facts">
            <template
              v-for="field in [
                { key: 'condition', label: '成色' },
                { key: 'bought', label: '购买时间' },
                { key: 'course', label: '适用课程' },
                { key: 'edition', label: '版次' },
                { key: 'publisher', label: '出版社' },
                { key: 'author', label: '作者' },
                { key: 'isbn', label: 'ISBN' },
                { key: 'notes', label: '笔记' },
                { key: 'missing', label: '缺页' },
                { key: 'accessories', label: '附件' },
                { key: 'region', label: '交付地点' },
                { key: 'delivery', label: '交付方式' },
              ]"
              :key="field.key"
              ><template v-if="text(listing.data.value, field.key)"
                ><dt>{{ field.label }}</dt>
                <dd>{{ text(listing.data.value, field.key) }}</dd></template
              ></template
            >
            <dt>送货费</dt>
            <dd>¥{{ money(number(listing.data.value, 'delivery_fee')) }}</dd>
          </dl>
          <RouterLink :to="'/users/' + number(listing.data.value, 'seller_id')"
            >{{ text(listing.data.value, 'nickname') }} · 查看卖家主页</RouterLink
          >
          <p class="muted">交付前当面核对版次、成色和缺陷。当前付款均为模拟。</p>
          <div v-if="own" class="actions">
            <AppButton
              v-if="['available', 'removed'].includes(text(listing.data.value, 'status'))"
              variant="secondary"
              :loading="action.busy.value"
              @click="
                manage(text(listing.data.value, 'status') === 'available' ? 'delist' : 'relist')
              "
              >{{
                text(listing.data.value, 'status') === 'available' ? '下架商品' : '重新上架'
              }}</AppButton
            ><RouterLink to="/my-products">管理我发布的</RouterLink>
          </div>
          <template v-else
            ><div class="actions">
              <AppButton
                :disabled="text(listing.data.value, 'status') !== 'available'"
                @click="add(true)"
                >立即下单</AppButton
              ><AppButton
                variant="secondary"
                :disabled="text(listing.data.value, 'status') !== 'available'"
                @click="add(false)"
                >加入清单</AppButton
              ><AppButton variant="quiet" @click="favorite">{{
                listing.data.value.favorited ? '取消收藏' : '收藏'
              }}</AppButton>
            </div>
            <form
              v-if="session.me && text(listing.data.value, 'status') === 'available'"
              class="inline-form"
              @submit.prevent="submitOffer"
            >
              <label
                >向卖家出价（元）<input
                  v-model="offer"
                  required
                  inputmode="decimal"
                  placeholder="如 15.00" /></label
              ><AppButton type="submit" variant="secondary" :loading="action.busy.value"
                >提交出价</AppButton
              >
            </form>
            <AppButton v-if="session.me" variant="quiet" @click="chat"
              >联系卖家</AppButton
            ></template
          ><RouterLink
            :to="{ path: '/support/new', query: { type: 'report', product: route.params.id } }"
            >举报商品</RouterLink
          >
        </section>
      </div>
      <section v-if="recommendations.data.value?.length" class="recommendations">
        <h2>再逛逛同学的闲置</h2>
        <div class="product-grid">
          <ProductCard
            v-for="product in recommendations.data.value"
            :key="number(product, 'id')"
            :product="product"
          />
        </div></section></template
  ></LoadBoundary>
</template>
