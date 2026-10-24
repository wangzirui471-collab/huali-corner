<script setup>
import { ref, onScopeDispose } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

import { row, children, text, number, money, date } from '@/shared/legacy/dto.js';
import { useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const route = useRoute(),
  action = useAction(),
  target = Number(route.params.id);
const dossier = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null)),
  chats = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null)),
  chat = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null));
const controller = new AbortController();
let active = true;
onScopeDispose(() => {
  active = false;
  controller.abort();
  dossier.value = null;
  chats.value = null;
  chat.value = null;
});
/** 查档会产生审计，必须由用户在说明后显式读取，不在挂载时预取。 */
async function load() {
  await action.run(async () => {
    const result = row(await api('/user/dossier?id=' + target, { signal: controller.signal }));
    if (active) dossier.value = result;
  }, '档案已读取，本次访问已记录审计');
}
/** 会话列表与正文分开授权读取，不能通过档案批量泄露聊天。 */
async function loadChats() {
  await action.run(async () => {
    const result = row(await api('/admin/chats?user_id=' + target, { signal: controller.signal }));
    if (active) chats.value = result;
  }, '已读取该用户参与的会话列表');
}
/** 每次查看正文均写服务端审计，不缓存到浏览器存储。 @param {number} room 会话编号。 */
async function readChat(room) {
  await action.run(async () => {
    const result = row(
      await api('/admin/chat?user_id=' + target + '&room_id=' + room, {
        signal: controller.signal,
      }),
    );
    if (active) chat.value = result;
  }, '本次聊天读取已记录审计');
}
</script>
<template>
  <section>
    <RouterLink to="/workspace/accounts">← 返回用户账号</RouterLink>
    <header class="section-heading">
      <div>
        <span class="eyebrow">AUDITED ACCESS</span>
        <h1>用户 #{{ target }} 的档案</h1>
      </div>
    </header>
    <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
    <section class="panel">
      <p>用户档案含个人资料与交易、工单记录。查阅将写入审计，仅用于当前核实工作。</p>
      <AppButton :loading="action.busy.value" @click="load">{{
        dossier ? '重新读取并记录访问' : '确认用途并读取档案'
      }}</AppButton>
    </section>
    <template v-if="dossier"
      ><section class="panel">
        <h2>{{ text(dossier.user ? row(dossier.user) : null, 'nickname') }}</h2>
        <p>脱敏账号：{{ text(dossier, 'phone') }}</p>
        <p>服务操作人 #{{ number(dossier, 'served_by') }}</p>
      </section>
      <section
        v-for="group in [
          { key: 'orders', label: '订单' },
          { key: 'products', label: '商品' },
          { key: 'tickets', label: '工单' },
          { key: 'posts', label: '帖子' },
          { key: 'comments', label: '评论' },
          { key: 'wants', label: '求购' },
          { key: 'reviews', label: '评价' },
          { key: 'audit', label: '信誉与处置记录' },
        ]"
        :key="group.key"
        class="panel"
      >
        <h2>{{ group.label }}</h2>
        <article
          v-for="(item, index) in children(dossier, group.key)"
          :key="number(item, 'id') || index"
          class="list-row"
        >
          <div>
            <b
              >#{{ number(item, 'id') }}
              {{
                text(item, 'title') ||
                text(item, 'subject') ||
                text(item, 'keyword') ||
                text(item, 'type')
              }}</b
            >
            <p class="description">{{ text(item, 'body') || text(item, 'reason') }}</p>
            <small
              >{{ text(item, 'status') }}
              {{ number(item, 'total') ? '¥' + money(number(item, 'total')) : '' }} ·
              {{ date(number(item, 'created')) }}</small
            >
          </div>
          <RouterLink v-if="group.key === 'tickets'" :to="'/support/' + number(item, 'id')"
            >工单详情</RouterLink
          ><RouterLink v-if="group.key === 'products'" :to="'/products/' + number(item, 'id')"
            >商品详情</RouterLink
          >
        </article>
        <p v-if="!children(dossier, group.key).length" class="muted">暂无记录</p>
      </section>
      <section class="panel">
        <h2>聊天记录访问</h2>
        <p class="muted">
          先读取会话清单，逐个点击查看正文。每次正文读取单独审计，最多显示最近 200 条。
        </p>
        <AppButton variant="secondary" :loading="action.busy.value" @click="loadChats"
          >读取会话清单</AppButton
        >
        <div v-for="room in children(chats, 'rooms')" :key="number(room, 'id')" class="list-row">
          <span>{{ text(room, 'name') }} · {{ number(room, 'message_count') }} 条</span
          ><AppButton variant="quiet" @click="readChat(number(room, 'id'))"
            >查看正文并记录审计</AppButton
          >
        </div>
      </section></template
    ><AppDialog :open="!!chat" title="审计查阅：聊天正文" @close="chat = null"
      ><p class="notice-panel">档案对象 #{{ target }}；此处仅供读取，离开页面清除内存。</p>
      <article
        v-for="message in children(chat, 'messages')"
        :key="number(message, 'id')"
        class="panel"
      >
        <small
          >{{ text(message, 'nickname') }}
          {{ number(message, 'user_id') === target ? '· 档案对象' : '' }} ·
          {{ date(number(message, 'created')) }}</small
        >
        <p class="description">
          {{ number(message, 'removed') === 2 ? '已撤回' : text(message, 'body') }}
        </p>
      </article></AppDialog
    >
  </section>
</template>
