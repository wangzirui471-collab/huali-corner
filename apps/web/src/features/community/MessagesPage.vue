<script setup>
import { computed, onScopeDispose, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, readStorage, writeStorage, roleRank } from '@/shared/legacy/session.js';
import { row, rows, children, text, number, date } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import { ApiError } from '@/shared/http/client.js';
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const route = useRoute(),
  router = useRouter(),
  action = useAction(),
  roomId = Number(route.params.id) || 0,
  noticesView = route.params.id === 'notice';
const membersOpen = ref(false),
  members = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null)),
  memberReason = ref('');
const outboxKey = `hc-vue-message-${number(session.me, 'id')}-${roomId}`;
/** 恢复本账号本会话的未确认消息，重试沿用原键。 */
function restore() {
  try {
    const saved = row(JSON.parse(readStorage(outboxKey, true) || '{}'));
    return typeof saved.key === 'string' && typeof saved.body === 'string'
      ? { key: saved.key, body: saved.body }
      : null;
  } catch {
    return null;
  }
}
const pending = ref(restore()),
  body = ref(pending.value?.body || '');
const rooms = useLoad(async (signal) => row(await api('/rooms', { signal })));
const notices = useLoad(async (signal) => row(await api('/notifications', { signal })));
const joined = computed(() => {
  const items = children(rooms.data.value, 'joined');
  if (rooms.data.value?.my_support) {
    const support = row(rooms.data.value.my_support);
    if (!items.some((item) => number(item, 'id') === number(support, 'id')))
      return [...items, support];
  }
  return items;
});
const room = computed(() => joined.value.find((item) => number(item, 'id') === roomId));
const messages = useLoad(async (signal) =>
  roomId ? rows(await api('/messages?room_id=' + roomId, { signal })) : [],
);
const receipts = useLoad(async (signal) =>
  roomId ? row(await api('/messages/receipts?room_id=' + roomId, { signal })) : null,
);
const timer = setInterval(() => {
  if (
    !document.hidden &&
    !action.busy.value &&
    !rooms.loading.value &&
    !messages.loading.value &&
    !notices.loading.value
  ) {
    void rooms.reload();
    void notices.reload();
    if (roomId) {
      void messages.reload();
      void receipts.reload();
    }
  }
}, 5000);
onScopeDispose(() => {
  clearInterval(timer);
  members.value = null;
  body.value = '';
  pending.value = null;
});
/** 同一条消息仅保留一个请求键；网络失败和 5xx 后不换键重发。 */
async function send() {
  await action.run(async () => {
    if (!body.value.trim()) throw new Error('请先填写消息');
    if (pending.value && pending.value.body !== body.value)
      throw new Error('上一条消息结果未确认，请先按原内容重试');
    pending.value ||= { key: crypto.randomUUID(), body: body.value };
    if (!writeStorage(outboxKey, JSON.stringify(pending.value), true))
      throw new Error('无法保存消息恢复信息，请允许会话存储');
    try {
      await api('/messages', { body: { room_id: roomId, ...pending.value } });
      pending.value = null;
      writeStorage(outboxKey, null, true);
      body.value = '';
      await messages.reload();
    } catch (error) {
      if (error instanceof ApiError && !error.outcomeUnknown) {
        pending.value = null;
        writeStorage(outboxKey, null, true);
      }
      throw error;
    }
  }, '消息已发送');
}
/** 客服先显式认领，认领失败不能假装已接入。 @param {import('@/shared/legacy/dto.js').Row} target 会话。 */
async function openRoom(target) {
  await action.run(async () => {
    if (target.support && roleRank() >= 1) {
      const claim = row(await api('/support/claim', { body: { room_id: number(target, 'id') } }));
      if (!claim.ok) throw new Error('该会话已由其他客服认领');
    }
    await router.push('/messages/' + number(target, 'id'));
  }, '会话已打开');
}
/** 进入平台已有总聊或学院群，不自建新的群 writer。 @param {string} kind 群种类。 */
async function join(kind) {
  await action.run(async () => {
    const result = row(await api('/rooms/join', { body: { kind } }));
    await router.push('/messages/' + number(result, 'id'));
  });
}
/** 撤回、仅对我隐藏、群处置使用各自接口；危险动作先确认。 @param {import('@/shared/legacy/dto.js').Row} message 消息。 @param {string} kind 动作。 */
async function messageAction(message, kind) {
  if (
    !window.confirm(
      kind === 'hide'
        ? '仅从你的视图隐藏这条消息？'
        : '确认处理这条消息？操作由服务端核对权限和时限。',
    )
  )
    return;
  if (kind === 'remove') {
    const entered = window.prompt('请填写移除消息的理由（记入审计）', memberReason.value);
    if (!entered?.trim()) return;
    memberReason.value = entered;
  }
  await action.run(async () => {
    await api(kind === 'remove' ? '/moderate' : '/messages/' + kind, {
      body:
        kind === 'remove'
          ? {
              room_id: roomId,
              action: 'remove_message',
              message_id: number(message, 'id'),
              reason: memberReason.value,
            }
          : { message_id: number(message, 'id') },
    });
    await messages.reload();
  }, '消息显示已更新');
}
/** 标记通知已读后仍保留通知正文与业务跳转入口。 @param {number} id 通知编号，0 代表全部。 */
async function readNotice(id = 0) {
  await action.run(async () => {
    await api('/notifications', { body: id ? { id } : {} });
    await notices.reload();
  }, '通知已标记已读');
}
/** 会话设置仍按当前成员权限由后端审核，清空仅影响本人可见记录。 @param {string} kind 设置。 */
async function roomAction(kind) {
  if (!room.value) return;
  if (kind === 'clear' && !window.confirm('仅清空自己可见的历史消息，其他成员仍可见。确认继续？'))
    return;
  await action.run(async () => {
    if (kind === 'block')
      await api('/block', {
        body: { target: number(room.value, 'peer_id'), enabled: !room.value?.blocked },
      });
    else if (kind === 'close') await api('/support/close', { body: { room_id: roomId } });
    else if (kind === 'release')
      await api('/support/claim', { body: { room_id: roomId, action: 'release' } });
    else await api('/rooms/' + kind, { body: { room_id: roomId, pinned: !room.value?.pinned } });
    await rooms.reload();
    await messages.reload();
  }, '会话设置已更新');
}
/** 成员资料只在当前会话中读取，离开时丢弃。 */
async function showMembers() {
  await action.run(async () => {
    members.value = row(await api('/room/members?room_id=' + roomId));
    membersOpen.value = true;
  }, '成员列表已更新');
}
/** 群禁言不是平台角色授权；服务端再次验证群管理身份。 @param {number} target 成员编号。 @param {boolean} muted 是否禁言。 */
async function moderate(target, muted) {
  const entered = window.prompt('请填写群禁言或解除禁言的理由（记入审计）', memberReason.value);
  if (!entered?.trim()) return;
  memberReason.value = entered;
  await action.run(async () => {
    await api('/moderate', {
      body: { room_id: roomId, action: 'mute', target, muted, reason: memberReason.value },
    });
    members.value = row(await api('/room/members?room_id=' + roomId));
  }, '群成员状态已更新');
}
/** 普通成员通过原提名入口申请群管理，不直接获得平台权限。 */
async function nominate() {
  await action.run(async () => {
    await api('/nominate', { body: { room_id: roomId, reason: memberReason.value } });
    memberReason.value = '';
  }, '群管理员申请已提交');
}
</script>
<template>
  <RouterLink v-if="roomId || noticesView" to="/messages" class="breadcrumbs"
    >← 返回消息列表</RouterLink
  >
  <header class="section-heading">
    <div>
      <span class="eyebrow">STAY CONNECTED</span>
      <h1>消息</h1>
    </div>
    <RouterLink to="/friends">好友与申请</RouterLink>
  </header>
  <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
  <div class="chat-layout" :class="{ 'chat-detail': roomId || noticesView }">
    <aside class="panel room-list">
      <RouterLink to="/messages/notice" class="room-row"
        >站内通知 <b>{{ number(notices.data.value, 'unread') || '' }}</b></RouterLink
      ><LoadBoundary :loading="rooms.loading.value" :error="rooms.error.value" @retry="rooms.reload"
        ><button
          v-for="entry in joined"
          :key="number(entry, 'id')"
          class="room-row"
          :aria-current="number(entry, 'id') === roomId ? 'page' : undefined"
          @click="openRoom(entry)"
        >
          <span
            ><b>{{
              text(entry, 'name') || text(entry, 'peer_name', '会话 #' + number(entry, 'id'))
            }}</b
            ><small>{{ text(entry, 'last_body') || text(entry, 'online_hint') }}</small></span
          ><span v-if="number(entry, 'unread')" class="badge">{{ number(entry, 'unread') }}</span>
        </button>
        <div class="form-stack">
          <AppButton variant="secondary" @click="join('general')">加入校园总聊</AppButton
          ><AppButton variant="secondary" @click="join('college')">加入学院群</AppButton>
        </div></LoadBoundary
      >
    </aside>
    <section class="panel chat-main">
      <template v-if="noticesView"
        ><header class="section-heading">
          <h2>站内通知</h2>
          <AppButton variant="quiet" @click="readNotice(0)">全部已读</AppButton>
        </header>
        <LoadBoundary
          :loading="notices.loading.value"
          :error="notices.error.value"
          @retry="notices.reload"
          ><article
            v-for="notice in children(notices.data.value, 'items')"
            :key="number(notice, 'id')"
            class="timeline-entry"
          >
            <p>{{ text(notice, 'body') }}</p>
            <small>{{ date(number(notice, 'created')) }}</small>
            <div class="actions">
              <RouterLink v-if="number(notice, 'order_id')" to="/orders">查看订单</RouterLink
              ><RouterLink
                v-if="number(notice, 'ticket_id')"
                :to="'/support/' + number(notice, 'ticket_id')"
                >查看工单</RouterLink
              ><RouterLink
                v-if="number(notice, 'post_id')"
                :to="'/posts/' + number(notice, 'post_id')"
                >查看帖子</RouterLink
              ><button v-if="!notice.read_at" @click="readNotice(number(notice, 'id'))">
                标为已读
              </button>
            </div>
          </article></LoadBoundary
        ></template
      ><template v-else-if="roomId"
        ><header class="chat-heading">
          <RouterLink to="/messages" class="mobile-back">会话列表</RouterLink>
          <h2>{{ text(room, 'name', '会话 #' + roomId) }}</h2>
          <details>
            <summary>会话设置</summary>
            <div class="actions">
              <button @click="showMembers">成员</button
              ><button @click="roomAction('pin')">{{ room?.pinned ? '取消置顶' : '置顶' }}</button
              ><button @click="roomAction('clear')">清空我的记录</button
              ><button v-if="number(room, 'peer_id')" @click="roomAction('block')">
                {{ room?.blocked ? '取消拉黑' : '拉黑' }}</button
              ><template v-if="room?.support && roleRank() >= 1"
                ><button @click="roomAction('release')">释放认领</button
                ><button @click="roomAction('close')">结束接待</button></template
              >
            </div>
          </details>
        </header>
        <LoadBoundary
          :loading="messages.loading.value && !messages.data.value"
          :error="messages.error.value"
          :forbidden="messages.forbidden.value"
          @retry="messages.reload"
          ><p class="muted">显示最近 200 条消息；后台窗口暂停自动刷新。</p>
          <div class="message-list" role="log" aria-live="polite" aria-label="会话消息">
            <article
              v-for="message in messages.data.value"
              :key="number(message, 'id')"
              class="message"
              :class="{ 'message-own': number(message, 'user_id') === number(session.me, 'id') }"
            >
              <small
                >{{ text(message, 'nickname') }} · {{ date(number(message, 'created')) }}</small
              >
              <p class="description">
                {{ number(message, 'removed') === 2 ? '已撤回' : text(message, 'body') }}
              </p>
              <small
                v-if="number(message,'user_id')===number(session.me,'id') &amp;&amp; receipts.data.value"
                >已读
                {{
                  children(receipts.data.value, 'readers').filter(
                    (reader) => number(reader, 'last_read_id') >= number(message, 'id'),
                  ).length
                }}
                / {{ number(receipts.data.value, 'total') }}</small
              >
              <div class="message-tools">
                <button
                  v-if="number(message, 'user_id') === number(session.me, 'id') && !message.removed"
                  @click="messageAction(message, 'recall')"
                >
                  撤回</button
                ><button @click="messageAction(message, 'hide')">仅对我隐藏</button
                ><button
                  v-if="['owner', 'moderator'].includes(text(room, 'role')) || roleRank() >= 2"
                  @click="messageAction(message, 'remove')"
                >
                  移除消息
                </button>
              </div>
            </article>
            <p v-if="!messages.data.value?.length" class="muted">还没有消息，先打个招呼吧。</p>
          </div></LoadBoundary
        >
        <p v-if="pending" class="notice">上一条消息结果未确认，重试将沿用原请求键。</p>
        <form class="message-composer" @submit.prevent="send">
          <label class="sr-only" for="message-body">发送消息</label
          ><textarea
            id="message-body"
            v-model="body"
            required
            maxlength="2000"
            rows="3"
            :disabled="!!room?.blocked || !!room?.muted"
            placeholder="友善交流，保护隐私。Enter 换行，点击按钮发送。"
          /><AppButton
            type="submit"
            :loading="action.busy.value"
            :disabled="!!room?.blocked || !!room?.muted"
            >{{ pending ? '按原键重试' : '发送' }}</AppButton
          >
        </form></template
      >
      <div v-else class="chat-welcome">
        <span class="eyebrow">HUALI CORNER</span>
        <h2>与同学保持联系</h2>
        <p>选择会话，或先去好友页认识彼此。</p>
        <RouterLink to="/friends">查看好友 →</RouterLink>
      </div>
    </section>
  </div>
  <AppDialog :open="membersOpen" title="会话成员" @close="membersOpen = false"
    ><div
      v-for="member in children(members, 'members')"
      :key="number(member, 'user_id')"
      class="list-row"
    >
      <span>{{ text(member, 'nickname') }} · {{ text(member, 'role') }}</span
      ><AppButton
        v-if="
          (['owner', 'moderator'].includes(text(room, 'role')) || roleRank() >= 2) &&
          number(member, 'user_id') !== number(session.me, 'id')
        "
        variant="quiet"
        @click="moderate(number(member, 'user_id'), !member.muted)"
        >{{ member.muted ? '解除禁言' : '禁言' }}</AppButton
      >
    </div>
    <form class="form-stack" @submit.prevent="nominate">
      <label>申请群管理员的理由<textarea v-model="memberReason" required maxlength="500" /></label
      ><AppButton type="submit" variant="secondary">提交申请</AppButton>
      <p class="muted">群管理不包含客服或资金权限。</p>
    </form></AppDialog
  >
</template>
