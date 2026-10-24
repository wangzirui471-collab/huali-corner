<script setup>
import { computed, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { session } from "@/shared/legacy/session.js";
import { rows, text, number, date, money } from "@/shared/legacy/dto.js";
import { useLoad, useAction } from "@/shared/legacy/use-task.js";
import { useLegacyApi } from "@/shared/legacy/use-task.js";
import AppIcon from "@/shared/ui/AppIcon.vue";
const composeOpen = ref(false);
const api = useLegacyApi();
import { yuanToCents } from "@/features/trade/checkout.js";
import AppButton from "@/shared/ui/AppButton.vue";
import LoadBoundary from "@/shared/ui/LoadBoundary.vue";
import TaskFeedback from "@/shared/ui/TaskFeedback.vue";
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  moreLoading = ref(false),
  hasMore = ref(true);
const title = ref(""),
  body = ref(""),
  budget = ref(""),
  query = ref(String(route.query.q || "")),
  topic = ref("交流");
const forum = route.path.startsWith("/forum"),
  wants = route.params.board === "wants";
const boards = [
  { key: "", label: "论坛首页", topic: "" },
  { key: "wants", label: "校园求购", topic: "" },
  { key: "exchange", label: "交换人生", topic: "交换人生" },
  { key: "errand", label: "代拿快递", topic: "代拿快递" },
  { key: "account", label: "我的帖子", topic: "" },
];
const active = computed(
  () =>
    boards.find((board) => board.key === String(route.params.board || "")) ||
    boards[0],
);
const entries = ref(/** @type {import('@/shared/legacy/dto.js').Row[]} */ ([]));
/** 每页使用后端实际支持的 offset，不通过扩大 limit 越过封顶。 @param {number} offset 当前偏移。 */
function path(offset) {
  const params = new URLSearchParams({
    limit: "20",
    offset: String(offset),
    q: String(route.query.q || ""),
    sort: String(route.query.sort || "latest"),
  });
  if (active.value.topic) params.set("topic", active.value.topic);
  else if (forum && !wants) params.set("forum", "1");
  if (active.value.key === "account" && session.me)
    params.set("author", String(number(session.me, "id")));
  return (wants ? "/wants?" : "/posts?") + params;
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
    const ids = new Set(entries.value.map((entry) => number(entry, "id")));
    entries.value.push(
      ...result.filter((entry) => !ids.has(number(entry, "id"))),
    );
    hasMore.value = result.length === 20;
  }, "已加载更多");
  moreLoading.value = false;
}
/** 旧帖子以首行作为标题，保留整个正文；只有服务端成功后清空草稿。 */
async function compose() {
  if (!session.me) {
    await router.push({ path: "/login", query: { next: route.fullPath } });
    return;
  }
  await action.run(
    async () => {
      const content = title.value.trim() + "\n" + body.value.trim();
      await api(wants ? "/wants" : "/posts", {
        body: wants
          ? {
              keyword: title.value,
              budget: yuanToCents(budget.value),
              description: body.value,
            }
          : {
              topic: forum ? active.value.topic || "交换人生" : topic.value,
              body: content,
            },
      });
      title.value = "";
      body.value = "";
      budget.value = "";
      await feed.reload();
    },
    wants ? "求购已发布" : "帖子已发布",
  );
}
/** 搜索与排序保存在地址，便于返回、分享和另一台电脑验收。 */
function search() {
  void router.push({ query: { ...route.query, q: query.value || undefined } });
}
</script>
<template>
  <section
    class="social-review"
    :class="forum ? 'forum-review' : 'community-review'"
  >
    <header class="social-title">
      <div>
        <span class="review-kicker">{{
          forum ? "HUALI / DISCUSS" : "HUALI / CAMPUS LIFE"
        }}</span>
        <h1>{{ forum ? "校园论坛" : "校园里，总有新鲜事。" }}</h1>
        <p>
          {{
            forum
              ? "找到同频的人，一起把事情聊明白。"
              : "课间的发现、毕业的告别，还有想分享的小事。"
          }}
        </p>
      </div>
      <span class="social-symbol" aria-hidden="true"
        ><AppIcon :name="forum ? 'forum' : 'chat'" :size="52"
      /></span>
    </header>
    <div class="social-columns">
      <aside class="social-rail">
        <template v-if="forum">
          <span class="review-kicker">讨论板块</span>
          <nav aria-label="论坛板块">
            <RouterLink
              v-for="board in boards"
              :key="board.key"
              :to="'/forum' + (board.key ? '/' + board.key : '')"
              :aria-current="active.key === board.key ? 'page' : undefined"
              ><AppIcon
                :name="
                  board.key === 'wants'
                    ? 'search'
                    : board.key === 'errand'
                      ? 'bag'
                      : 'forum'
                "
                :size="18"
              />{{ board.label }}</RouterLink
            >
          </nav>
          <div class="rail-note">
            <span class="note-mark">先沟通，再约定</span>
            <p>交换、求购或顺路帮忙，时间地点和费用都要聊清楚。</p>
            <RouterLink to="/community">去看校园日常 →</RouterLink>
          </div>
        </template>
        <template v-else>
          <div class="rail-profile">
            <span class="review-avatar">{{
              text(session.me, "nickname", "同").slice(0, 1)
            }}</span>
            <h2>{{ text(session.me, "nickname", "校园同学") }}</h2>
            <p>欢迎回到你的校园。</p>
          </div>
          <nav aria-label="校园交流">
            <RouterLink to="/community" aria-current="page"
              ><AppIcon name="chat" :size="18" />校园动态</RouterLink
            ><RouterLink to="/friends"
              ><AppIcon name="user" :size="18" />好友与申请</RouterLink
            ><RouterLink to="/messages"
              ><AppIcon name="forum" :size="18" />学院群与总聊</RouterLink
            >
          </nav>
          <div class="rail-note">
            <span class="note-mark">把需要，交给同学</span>
            <p>想找教材、交换好书，去论坛聊一聊。</p>
            <RouterLink to="/forum/wants">发现校园求购 →</RouterLink>
          </div>
        </template>
      </aside>
      <div class="social-content">
        <div class="social-toolbar">
          <div>
            <span class="review-kicker">{{
              forum ? "DISCUSSIONS" : "MOMENTS"
            }}</span>
            <h2>
              {{ forum ? active.label : "最新动态"
              }}<small>{{ entries.length }} 条内容</small>
            </h2>
          </div>
          <button
            class="review-primary"
            type="button"
            aria-controls="review-compose"
            :aria-expanded="composeOpen"
            @click="composeOpen = !composeOpen"
          >
            <AppIcon :name="composeOpen ? 'close' : 'plus'" :size="18" />{{
              composeOpen
                ? "收起编辑"
                : wants
                  ? "发布求购"
                  : forum
                    ? "发起话题"
                    : "分享日常"
            }}
          </button>
        </div>
        <form
          v-show="composeOpen"
          id="review-compose"
          class="review-compose form-stack"
          @submit.prevent="compose"
        >
          <h3>
            {{
              wants
                ? "说说你想找什么"
                : forum
                  ? "发起一个新话题"
                  : "今天有什么想分享？"
            }}
          </h3>
          <label v-if="!forum"
            >话题<select v-model="topic">
              <option>交流</option>
              <option>毕业季</option>
              <option>互助</option>
            </select></label
          >
          <label for="review-title">{{ wants ? "想找什么" : "标题" }}</label
          ><input id="review-title" v-model="title" required maxlength="72" />
          <label v-if="wants"
            >预算（元）<input v-model="budget" required inputmode="decimal"
          /></label>
          <label
            >详细说明<textarea
              v-model="body"
              required
              maxlength="1000"
              rows="4"
            />
          </label>
          <div class="compose-bottom">
            <span>公开内容请保护个人隐私。</span
            ><AppButton type="submit" :loading="action.busy.value">{{
              session.me ? "发布" : "登录后发布"
            }}</AppButton>
          </div>
        </form>
        <TaskFeedback
          :error="action.error.value"
          :notice="action.notice.value"
        />
        <form class="review-search" @submit.prevent="search">
          <AppIcon name="search" :size="18" /><input
            v-model="query"
            :aria-label="wants ? '搜索求购' : '搜索帖子'"
            :placeholder="forum ? '搜索话题、关键词…' : '发现同学们在聊什么…'"
          /><button type="submit">搜索</button>
        </form>
        <div v-if="forum" class="thread-caption" aria-hidden="true">
          <span>话题 / 发起人</span><span>{{ wants ? "预算" : "回复" }}</span>
        </div>
        <LoadBoundary
          :loading="feed.loading.value"
          :error="feed.error.value"
          :empty="!!feed.data.value && !entries.length"
          @retry="feed.reload"
        >
          <article
            v-for="entry in entries"
            :key="number(entry, 'id')"
            :class="forum ? 'review-thread' : 'review-moment'"
          >
            <RouterLink
              :to="'/users/' + number(entry, 'user_id')"
              class="review-avatar"
              :aria-label="text(entry, 'nickname') + '的个人资料'"
              >{{ text(entry, "nickname", "同").slice(0, 1) }}</RouterLink
            >
            <div class="post-copy">
              <header class="post-meta">
                <RouterLink :to="'/users/' + number(entry, 'user_id')">{{
                  text(entry, "nickname")
                }}</RouterLink
                ><time>{{ date(number(entry, "created")) }}</time
                ><span v-if="text(entry, 'topic')" class="topic-label"
                  ># {{ text(entry, "topic") }}</span
                >
              </header>
              <RouterLink
                class="post-title"
                :to="(wants ? '/wants/' : '/posts/') + number(entry, 'id')"
                ><h3>
                  {{
                    wants
                      ? text(entry, "keyword")
                      : text(entry, "body").split("\n")[0]
                  }}
                </h3></RouterLink
              >
              <p class="post-description">
                {{
                  wants
                    ? text(entry, "description")
                    : text(entry, "body").split("\n").slice(1).join("\n") ||
                      text(entry, "body")
                }}
              </p>
              <footer>
                <RouterLink
                  :to="(wants ? '/wants/' : '/posts/') + number(entry, 'id')"
                  ><AppIcon :name="wants ? 'search' : 'chat'" :size="16" />{{
                    wants
                      ? "查看匹配"
                      : forum
                        ? "进入讨论"
                        : number(entry, "replies") + " 条评论"
                  }}</RouterLink
                ><RouterLink
                  class="post-report"
                  :to="{ path: '/support/new', query: { type: 'report' } }"
                  >举报</RouterLink
                >
              </footer>
            </div>
            <RouterLink
              v-if="forum"
              class="thread-count"
              :to="(wants ? '/wants/' : '/posts/') + number(entry, 'id')"
              ><b>{{
                wants
                  ? "¥" + money(number(entry, "budget"))
                  : number(entry, "replies")
              }}</b
              ><span>{{ wants ? "求购预算" : "回复" }}</span></RouterLink
            >
          </article>
          <AppButton
            v-if="hasMore"
            variant="secondary"
            :loading="moreLoading"
            @click="more"
            >加载更多</AppButton
          >
        </LoadBoundary>
        <p class="social-end">友善交流，让每一次相遇都舒服一点。</p>
      </div>
    </div>
  </section>
</template>
