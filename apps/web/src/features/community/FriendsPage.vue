<script setup>
import { reactive } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

import { row, children, text, number } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import AppButton from '@/shared/ui/AppButton.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const router = useRouter(),
  action = useAction(),
  form = reactive({ target: String(useRoute().query.target || ''), message: '' });
const friends = useLoad(async (signal) => row(await api('/friends', { signal })));
/** 好友请求保留简短附言，服务端核对目标身份和重复申请。 */
async function request() {
  await action.run(async () => {
    await api('/friend/request', {
      body: { target: Number(form.target), message: form.message, want_id: 0 },
    });
    form.message = '';
    await friends.reload();
  }, '好友申请已发送');
}
/** 接受或拒绝申请后刷新，不以本地推断代替好友关系。 @param {number} id 申请编号。 @param {boolean} accept 是否接受。 */
async function decide(id, accept) {
  await action.run(async () => {
    await api('/friend/decide', { body: { id, accept } });
    await friends.reload();
  }, '好友申请已处理');
}
/** 私聊入口继续使用服务端好友与拉黑检查。 @param {number} peer 好友用户编号。 */
async function chat(peer) {
  await action.run(async () => {
    const room = row(await api('/rooms/private', { body: { peer } }));
    await router.push('/messages/' + number(room, 'id'));
  });
}
</script>
<template>
  <header class="section-heading">
    <div>
      <span class="eyebrow">CAMPUS CONNECTIONS</span>
      <h1>好友与申请</h1>
      <p class="muted">先成为好友，再开启普通私聊。</p>
    </div>
    <RouterLink to="/messages">返回消息</RouterLink>
  </header>
  <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
  <div class="community-layout">
    <LoadBoundary
      :loading="friends.loading.value"
      :error="friends.error.value"
      @retry="friends.reload"
      ><div class="form-stack">
        <section
          v-for="group in [
            { key: 'incoming', label: '收到的申请' },
            { key: 'friends', label: '我的好友' },
            { key: 'outgoing', label: '发出的申请' },
          ]"
          :key="group.key"
          class="panel"
        >
          <h2>{{ group.label }}</h2>
          <article
            v-for="friend in children(friends.data.value, group.key)"
            :key="number(friend, 'id')"
            class="list-row"
          >
            <div>
              <RouterLink :to="'/users/' + number(friend, 'user_id')">{{
                text(friend, 'nickname')
              }}</RouterLink>
              <p class="muted">{{ text(friend, 'college') }} · {{ text(friend, 'message') }}</p>
            </div>
            <div class="actions">
              <template v-if="group.key === 'incoming'"
                ><AppButton variant="secondary" @click="decide(number(friend, 'id'), true)"
                  >接受</AppButton
                ><AppButton variant="quiet" @click="decide(number(friend, 'id'), false)"
                  >拒绝</AppButton
                ></template
              ><AppButton
                v-else-if="group.key === 'friends'"
                variant="secondary"
                @click="chat(number(friend, 'user_id'))"
                >发消息</AppButton
              ><span v-else>等待对方同意</span>
            </div>
          </article>
          <p v-if="!children(friends.data.value, group.key).length" class="muted">暂无记录</p>
        </section>
      </div></LoadBoundary
    >
    <form class="panel form-stack" @submit.prevent="request">
      <h2>添加同学</h2>
      <label>用户编号<input v-model="form.target" required type="number" min="1" /></label
      ><label
        >简短附言<input v-model="form.message" maxlength="15" placeholder="说说你想聊什么" /></label
      ><AppButton type="submit" :loading="action.busy.value">发送申请</AppButton>
    </form>
  </div>
</template>
