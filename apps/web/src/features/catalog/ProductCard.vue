<script setup>
import { computed, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session } from '@/shared/legacy/session.js';
import { useAction, useLegacyApi } from '@/shared/legacy/use-task.js';
import { text, number, children, money, statusLabel } from '@/shared/legacy/dto.js';
import AppIcon from '@/shared/ui/AppIcon.vue';
import CatalogPhoto from './CatalogPhoto.vue';
import { demoPhotoIndex } from './photo.js';
import './catalog-card.css';
const props = defineProps({
  product: {
    type: /** @type {import('vue').PropType<import('@/shared/legacy/dto.js').Row>} */ (Object),
    required: true,
  },
});
const emit = defineEmits({
  'favorite-changed': (/** @type {{id:number,on:boolean}} */ result) => Number.isInteger(result.id),
});
const api = useLegacyApi(),
  action = useAction(),
  router = useRouter(),
  route = useRoute();
const favorited = ref(!!props.product.favorited);
watch(
  () => props.product.favorited,
  (value) => {
    favorited.value = !!value;
  },
);
const photo = computed(
  () => text(children(props.product, 'photos')[0], 'url') || text(props.product, 'photo'),
);
const demo = computed(() => demoPhotoIndex(!!props.product.simulation, photo.value) !== null);
const own = computed(
  () => !!session.me && number(props.product, 'seller_id') === number(session.me, 'id'),
);
const delivery = computed(() => {
  const kind = text(props.product, 'delivery'),
    fee = money(number(props.product, 'delivery_fee'));
  if (kind === 'pickup') return '校内自提';
  if (kind === 'delivery') return '仅卖家送货 · 运费 ¥' + fee;
  if (kind === 'both') return '可自提 / 送货 ¥' + fee;
  return '交付方式看详情';
});
/** 游客先登录；绝对 on 值写入成功才更新卡片和列表，失败保留旧状态。 */
async function favorite() {
  if (!session.me) {
    await router.push({ path: '/login', query: { next: route.fullPath } });
    return;
  }
  const on = !favorited.value;
  await action.run(
    async () => {
      await api('/react', {
        body: { product_id: number(props.product, 'id'), kind: 'favorite', on },
      });
      favorited.value = on;
      emit('favorite-changed', { id: number(props.product, 'id'), on });
    },
    on ? '已收藏；收藏不会预留商品。' : '已取消收藏',
  );
}
</script>
<template>
  <article class="product-card catalog-card">
    <div class="cover-wrap">
      <RouterLink
        :to="'/products/' + number(product, 'id')"
        class="product-cover"
        :aria-label="'查看' + text(product, 'title')"
        ><CatalogPhoto
          :src="photo"
          :alt="text(product, 'title')"
          :simulation="!!product.simulation"
      /></RouterLink>
      <span v-if="product.simulation" class="demo-tag">{{ demo ? 'AI 演示图' : '示例商品' }}</span>
      <button
        v-if="!own"
        class="favorite-button"
        :class="{ saved: favorited }"
        :aria-label="(favorited ? '取消收藏' : '收藏') + text(product, 'title')"
        :aria-pressed="favorited"
        :aria-busy="action.busy.value || undefined"
        :disabled="action.busy.value"
        @click="favorite"
      >
        <AppIcon name="heart" :size="20" />
      </button>
    </div>
    <div class="product-copy">
      <RouterLink :to="'/products/' + number(product, 'id')" class="product-title">{{
        text(product, 'title')
      }}</RouterLink>
      <div class="condition-line">
        <span>{{
          text(product, 'category') === 'books'
            ? text(product, 'edition', '版次看详情')
            : text(product, 'condition', '成色看详情')
        }}</span
        ><span class="place"
          ><AppIcon name="pin" :size="12" />{{ text(product, 'region', '地点看详情') }}</span
        >
      </div>
      <div class="price-line">
        <b v-if="number(product, 'price')"><small>¥</small>{{ money(number(product, 'price')) }}</b
        ><b v-else class="free-price">免费送</b
        ><del
          v-if="
            number(product, 'original_price') > number(product, 'price') && number(product, 'price')
          "
          >¥{{ money(number(product, 'original_price')) }}</del
        ><span
          v-if="text(product, 'status') && text(product, 'status') !== 'available'"
          class="card-status"
          >{{ statusLabel(text(product, 'status')) }}</span
        >
      </div>
      <p class="delivery-line">
        {{ number(product, 'price') === 0 ? '物品免费 · ' : '' }}{{ delivery }}
      </p>
      <div class="seller-line">
        <RouterLink :to="'/users/' + number(product, 'seller_id')" class="seller-link"
          ><span class="seller-avatar">{{ text(product, 'nickname', '同学').slice(0, 1) }}</span
          >{{ text(product, 'nickname', '华立同学') }}</RouterLink
        ><span v-if="product.seller_trusted" class="seller-trusted">诚信客户</span>
      </div>
      <p v-if="action.error.value" class="card-error" role="alert">
        {{ action.error.value
        }}<button :disabled="action.busy.value" @click="favorite">重试收藏</button>
      </p>
      <span class="sr-only" role="status">{{ action.notice.value }}</span>
    </div>
  </article>
</template>
