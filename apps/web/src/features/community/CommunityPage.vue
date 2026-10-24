<script setup>
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session } from '@/shared/legacy/session.js';
import { rows, text, number, date, money } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import { yuanToCents } from '@/features/trade/checkout.js';
import AppButton from '@/shared/ui/AppButton.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  moreLoading = ref(false),
  hasMore = ref(true);
const title = ref(''),
  body = ref(''),
  budget = ref(''),
  query = ref(String(route.query.q || '')),
  topic = ref('交流');
const forum = route.path.startsWith('/forum'),
  wants = route.params.board === 'wants';
const boards = [
  { key: '', label: '论坛首页', topic: '' },
  { key: 'wants', label: '校园求购', topic: '' },
  { key: 'exchange', label: '交换人生', topic: '交换人生' },
  { key: 'errand', label: '代拿快递', topic: '代拿快递' },
  { key: 'account', label: '我的帖子', topic: '' },
];
const active = computed(
  () => boards.find((board) => board.key === String(route.params.board || '')) || boards[0],
);
const entries = ref(/** @type {import('@/shared/legacy/dto.js').Row[]} */ ([]));
/** 每页使用后端实际支持的 offset，不通过扩大 limit 越过封顶。 @param {number} offset 当前偏移。 */
function path(offset) {
  const params = new URLSearchParams({
    limit: '20',
    offset: String(offset),
    q: String(route.query.q || ''),
    sort: String(route.query.sort || 'latest'),
  });
  if (active.value.topic) params.set('topic', active.value.topic);
  else if (forum && !wants) params.set('forum', '1');
  if (active.value.key === 'account' && session.me)
    params.set('author', String(number(session.me, 'id')));
  return (wants ? '/wants?' : '/posts?') + params;
}
const feed = useLoad(async (signal) => {
  const result = rows(await api(path(0), { signal }));
  entries.value = result;
  hasMore.value = result.length === 20;
  return result;
});
/** 追加失败保留已有列表与偏移，下一次仍取同一页。 */
async function more() {
  if (moreLoading.value) return;
  moreLoading.value = true;
  await action.run(async () => {
    const result = rows(await api(path(entries.value.length)));
    const ids = new Set(entries.value.map((entry) => number(entry, 'id')));
    entries.value.push(...result.filter((entry) => !ids.has(number(entry, 'id'))));
    hasMore.value = result.length === 20;
  }, '已加载更多');
  moreLoading.value = false;
}
/** 旧帖子以首行作为标题，保留整个正文；只有服务端成功后清空草稿。 */
async function compose() {
  if (!session.me) {
    await router.push({ path: '/login', query: { next: route.fullPath } });
    return;
  }
  await action.run(
    async () => {
      const content = title.value.trim() + '\n' + body.value.trim();
      await api(wants ? '/wants' : '/posts', {
        body: wants
          ? { keyword: title.value, budget: yuanToCents(budget.value), description: body.value }
          : { topic: forum ? active.value.topic || '交换人生' : topic.value, body: content },
      });
      title.value = '';
      body.value = '';
      budget.value = '';
      await feed.reload();
    },
    wants ? '求购已发布' : '帖子已发布',
  );
}
/** 搜索与排序保存在地址，便于返回、分享和另一台电脑验收。 */
function search() {
  void router.push({ query: { ...route.query, q: query.value || undefined } });
}
</script>
<template>
  <header class="community-hero">
    <div>
      <span class="eyebrow">{{ forum ? 'CAMPUS FORUM' : 'CAMPUS COMMUNITY' }}</span>
      <h1>{{ forum ? active.label : '校园社区' }}</h1>
      <p>自由交流，分享日常，也聊聊校园生活。</p>
    </div>
    <RouterLink :to="forum ? '/community' : '/forum/wants'"
      >{{ forum ? '去校园社区' : '去论坛求购' }} ↗</RouterLink
    >
  </header>
  <nav v-if="forum" class="tabs panel" aria-label="论坛板块">
    <RouterLink
      v-for="board in boards"
      :key="board.key"
      :to="'/forum' + (board.key ? '/' + board.key : '')"
      >{{ board.label }}</RouterLink
    >
  </nav>
  <div class="community-layout">
    <section class="form-stack">
      <form class="search-bar" @submit.prevent="search">
        <input
          v-model="query"
          :aria-label="wants ? '搜索求购' : '搜索帖子'"
          placeholder="寻找校园里的声音"
        /><button>搜索</button>
      </form>
      <TaskFeedback :error="action.error.value" :notice="action.notice.value" /><LoadBoundary
        :loading="feed.loading.value"
        :error="feed.error.value"
        :empty="!!feed.data.value && !entries.length"
        @retry="feed.reload"
        ><article v-for="entry in entries" :key="number(entry, 'id')" class="panel community-post">
          <header>
            <RouterLink :to="'/users/' + number(entry, 'user_id')">{{
              text(entry, 'nickname')
            }}</RouterLink
            ><small>{{ date(number(entry, 'created')) }} · {{ text(entry, 'topic') }}</small>
          </header>
          <RouterLink :to="(wants ? '/wants/' : '/posts/') + number(entry, 'id')"
            ><h2>
              {{ wants ? text(entry, 'keyword') : text(entry, 'body').split('\n')[0] }}
            </h2></RouterLink
          >
          <p class="description">
            {{
              wants
                ? text(entry, 'description')
                : text(entry, 'body').split('\n').slice(1).join('\n') || text(entry, 'body')
            }}
          </p>
          <footer>
            <b v-if="wants">预算 ¥{{ money(number(entry, 'budget')) }}</b
            ><RouterLink :to="(wants ? '/wants/' : '/posts/') + number(entry, 'id')"
              >{{ wants ? '查看匹配' : '评论 / 回复 ' + number(entry, 'replies') }} →</RouterLink
            ><RouterLink :to="{ path: '/support/new', query: { type: 'report' } }">举报</RouterLink>
          </footer>
        </article>
        <AppButton v-if="hasMore" variant="secondary" :loading="moreLoading" @click="more"
          >加载更多</AppButton
        ></LoadBoundary
      >
    </section>
    <aside class="form-stack">
      <form class="panel form-stack" @submit.prevent="compose">
        <h2>{{ wants ? '发布求购' : '分享校园日常' }}</h2>
        <label v-if="!forum"
          >话题<select v-model="topic">
            <option>交流</option>
            <option>毕业季</option>
            <option>互助</option>
          </select></label
        ><label
          >{{ wants ? '想找什么' : '标题' }}<input v-model="title" required maxlength="72" /></label
        ><label v-if="wants"
          >预算（元）<input v-model="budget" required inputmode="decimal" /></label
        ><label>详细说明<textarea v-model="body" required maxlength="1000" rows="6" /></label
        ><AppButton type="submit" :loading="action.busy.value">{{
          session.me ? '发布' : '登录后发布'
        }}</AppButton>
      </form>
      <section class="panel">
        <h2>交流之前</h2>
        <p>尊重彼此，友善交流。时间、地点与费用先沟通，公开内容中保护个人隐私。</p>
        <RouterLink to="/messages">学院群与总聊</RouterLink><br /><RouterLink to="/friends"
          >好友与申请</RouterLink
        >
      </section>
    </aside>
  </div>
</template>
