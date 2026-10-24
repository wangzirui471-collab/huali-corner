<script setup>
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, changeCart, writeStorage } from '@/shared/legacy/session.js';
import { row, rows, children, text, number, date, money } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import ProductCard from '@/features/catalog/ProductCard.vue';
import AppButton from '@/shared/ui/AppButton.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  isWant = route.path.startsWith('/wants/'),
  id = Number(route.params.id),
  body = ref(''),
  replyTo = ref(0),
  replyName = ref(''),
  message = ref('');
const replies = ref(/** @type {import('@/shared/legacy/dto.js').Row[]} */ ([])),
  hasMore = ref(false);
const post = useLoad(async (signal) => {
  if (isWant) return row(await api('/want?id=' + id, { signal }));
  const items = rows(await api('/posts?id=' + id, { signal }));
  if (!items[0]) throw new Error('帖子不存在或已不可见');
  return items[0];
});
const comments = useLoad(async (signal) => {
  if (isWant) return [];
  const items = rows(await api('/comments?id=' + id + '&limit=20&order=asc&after=0', { signal }));
  replies.value = items;
  hasMore.value = items.length === 20;
  return items;
});
const title = computed(() =>
  isWant ? text(post.data.value, 'keyword') : text(post.data.value, 'body').split('\n')[0],
);
/** 回复明确携带父评论编号，失败不丢输入。 */
async function reply() {
  if (!session.me) {
    await router.push({ path: '/login', query: { next: route.fullPath } });
    return;
  }
  await action.run(async () => {
    await api('/comments', { body: { post_id: id, parent_id: replyTo.value, body: body.value } });
    body.value = '';
    replyTo.value = 0;
    replyName.value = '';
    await comments.reload();
  }, '回复已发布');
}
/** 后续评论以服务端编号游标读取，去重保留回复关系。 */
async function more() {
  await action.run(async () => {
    const after = Math.max(0, ...replies.value.map((item) => number(item, 'id')));
    const items = rows(await api(`/comments?id=${id}&limit=20&order=asc&after=${after}`));
    const existing = new Set(replies.value.map((item) => number(item, 'id')));
    replies.value.push(...items.filter((item) => !existing.has(number(item, 'id'))));
    hasMore.value = items.length === 20;
  }, '评论已更新');
}
/** 求购撮合只在来源商品仍在清单时保留，供旧后端统一核算服务费。 @param {number} product 商品编号。 */
async function buy(product) {
  if (!session.me) {
    await router.push('/login');
    return;
  }
  await action.run(async () => {
    changeCart(product);
    writeStorage(
      `hc-vue-want-${number(session.me, 'id')}`,
      JSON.stringify({ want: id, product }),
      true,
    );
    await router.push('/cart');
  });
}
/** 我能卖先发送带求购上下文的好友申请，不绕过陌生人私聊门槛。 */
async function respond() {
  await action.run(async () => {
    await api('/friend/request', {
      body: { target: number(post.data.value, 'user_id'), want_id: id, message: message.value },
    });
    message.value = '';
  }, '好友申请已发送，对方同意后可沟通');
}
</script>
<template>
  <LoadBoundary
    :loading="post.loading.value"
    :error="post.error.value"
    :forbidden="post.forbidden.value"
    @retry="post.reload"
    ><template v-if="post.data.value"
      ><nav class="breadcrumbs">
        <RouterLink :to="isWant ? '/forum/wants' : '/forum'">{{
          isWant ? '校园求购' : '校园论坛'
        }}</RouterLink>
        / 详情
      </nav>
      <article class="panel reading-panel">
        <span class="eyebrow">{{ isWant ? 'CAMPUS WANTED' : text(post.data.value, 'topic') }}</span>
        <h1>{{ title }}</h1>
        <p class="muted">
          <RouterLink :to="'/users/' + number(post.data.value, 'user_id')">{{
            text(post.data.value, 'nickname')
          }}</RouterLink>
          · {{ date(number(post.data.value, 'created')) }}
        </p>
        <p class="description">
          {{ isWant ? text(post.data.value, 'description') : text(post.data.value, 'body') }}
        </p>
        <p v-if="isWant">
          <b>预算 ¥{{ money(number(post.data.value, 'budget')) }}</b> ·
          {{ text(post.data.value, 'status') === 'matched' ? '已成交' : '正在寻找' }}
        </p>
        <RouterLink to="/support/new?type=report">举报或寻求帮助</RouterLink>
      </article>
      <TaskFeedback :error="action.error.value" :notice="action.notice.value" /><template
        v-if="isWant"
        ><form
          v-if="
            session.me &&
            number(post.data.value, 'user_id') !== number(session.me, 'id') &&
            text(post.data.value, 'status') !== 'matched'
          "
          class="panel inline-form"
          @submit.prevent="respond"
        >
          <label
            >我能卖 · 发一条好友申请附言<input
              v-model="message"
              maxlength="15"
              placeholder="说明你有的物品与成色" /></label
          ><AppButton type="submit" :loading="action.busy.value">发送申请</AppButton>
        </form>
        <h2>匹配的在售商品</h2>
        <div class="product-grid">
          <div v-for="product in children(post.data.value, 'matches')" :key="number(product, 'id')">
            <ProductCard :product="product" /><AppButton
              v-if="
                number(post.data.value, 'user_id') === number(session.me, 'id') &&
                number(product, 'seller_id') !== number(session.me, 'id')
              "
              @click="buy(number(product, 'id'))"
              >我要这个 · 关联求购</AppButton
            >
          </div>
        </div>
        <p v-if="!children(post.data.value, 'matches').length" class="panel muted">
          暂时没有匹配的在售商品，稍后再来看看。
        </p></template
      >
      <section v-else class="panel reading-panel">
        <h2>评论与回复</h2>
        <LoadBoundary
          :loading="comments.loading.value"
          :error="comments.error.value"
          @retry="comments.reload"
          ><article
            v-for="comment in replies"
            :key="number(comment, 'id')"
            class="timeline-entry"
            :class="{ 'reply-entry': number(comment, 'parent_id') > 0 }"
          >
            <header>
              <b>{{ text(comment, 'nickname') }}</b
              ><small>{{ date(number(comment, 'created')) }}</small>
            </header>
            <p v-if="number(comment, 'parent_id')" class="muted">
              回复 #{{ number(comment, 'parent_id') }}
            </p>
            <p class="description">{{ text(comment, 'body') }}</p>
            <button
              class="text-action"
              @click="
                replyTo = number(comment, 'id');
                replyName = text(comment, 'nickname');
              "
            >
              回复
            </button>
          </article>
          <AppButton v-if="hasMore" variant="secondary" @click="more">加载后续评论</AppButton>
          <p v-if="!replies.length" class="muted">还没有评论，来说两句吧。</p></LoadBoundary
        >
        <form class="form-stack" @submit.prevent="reply">
          <p v-if="replyTo">
            回复 {{ replyName }}
            <button
              type="button"
              @click="
                replyTo = 0;
                replyName = '';
              "
            >
              取消回复
            </button>
          </p>
          <label>说点什么<textarea v-model="body" required maxlength="1000" rows="4" /></label
          ><AppButton type="submit" :loading="action.busy.value">{{
            session.me ? '发布回复' : '登录后回复'
          }}</AppButton>
        </form>
      </section></template
    ></LoadBoundary
  >
</template>
