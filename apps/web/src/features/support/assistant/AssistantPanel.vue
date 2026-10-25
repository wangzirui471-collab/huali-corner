<script setup>
import { useRouter } from 'vue-router';
import AppButton from '@/shared/ui/AppButton.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import { session } from '@/shared/legacy/session.js';
import { useAssistant } from './use-assistant.js';
import { saveAssistantDraft } from './handoff-draft.js';

const router = useRouter();
const { state, submit } = useAssistant();
/** 仅导航到可检查和编辑的人工表单，保留原人工提交及在线客服规则。 */
async function handoff() {
  saveAssistantDraft(state.question);
  await router.push('/support/new');
}
</script>

<template>
  <section class="panel form-stack assistant-panel" aria-labelledby="assistant-title">
    <div>
      <h2 id="assistant-title">公开规则问答</h2>
      <p class="muted">
        可询问模拟付款、同卖家送货费、发布照片等公开规则。请勿填写电话、密码或私密订单资料。
      </p>
    </div>
    <p v-if="!session.token" class="muted">请先登录后使用规则问答。</p>
    <form v-else class="form-stack" @submit.prevent="submit">
      <label for="assistant-question">你的问题</label>
      <textarea
        id="assistant-question"
        v-model="state.question"
        rows="3"
        maxlength="800"
        required
        placeholder="例如：付款会真实扣款吗？"
      />
      <div class="assistant-actions">
        <AppButton type="submit" :loading="state.busy">{{
          state.busy ? '正在查询' : '查询公开规则'
        }}</AppButton>
        <AppButton
          v-if="state.error && state.turn && !state.forbidden"
          data-action="retry"
          variant="quiet"
          :disabled="state.busy"
          @click="submit"
          >重试本次问题</AppButton
        >
      </div>
    </form>
    <TaskFeedback :error="state.error" />
    <p v-if="state.busy" role="status" class="muted">正在查询公开资料，请稍候。</p>
    <div v-else-if="state.answer" class="form-stack" aria-live="polite">
      <p v-if="state.answer.mode === 'mock'" class="muted">模拟回答 · 未调用真实模型</p>
      <p class="description assistant-text">{{ state.answer.answer_text }}</p>
      <div v-if="state.answer.sources.length">
        <h3>参考资料</h3>
        <details
          v-for="source in state.answer.sources"
          :key="source.document_id + ':' + source.version"
        >
          <summary>{{ source.title }} · {{ source.version }}</summary>
          <p class="description assistant-text">{{ source.content }}</p>
        </details>
      </div>
      <p v-else class="muted">暂无可核实来源，可提交问题由人工确认。</p>
      <p v-if="state.answer.handoff.recommended" class="description assistant-text">
        {{ state.answer.handoff.reason }}
      </p>
    </div>
    <div v-if="session.token" class="assistant-actions">
      <AppButton data-action="handoff" variant="quiet" :disabled="state.busy" @click="handoff"
        >转人工：填写问题</AppButton
      >
      <small class="muted">填写后由你确认提交，不会自动创建工单。</small>
    </div>
  </section>
</template>

<style scoped>
.assistant-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-12);
}
.assistant-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.assistant-panel details {
  padding-block: var(--space-8);
  border-bottom: 1px solid var(--color-border);
}
.assistant-panel summary {
  cursor: pointer;
  color: var(--color-link);
  overflow-wrap: anywhere;
}
</style>
