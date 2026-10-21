<script setup>
import { computed } from 'vue';
import { ElAlert } from 'element-plus';
import 'element-plus/theme-chalk/el-alert.css';

/** Element Plus 持久提示适配，关键失败保留文字与操作上下文。 */
const props = defineProps({
  tone: { type: String, default: 'info' },
  title: { type: String, required: true },
});
const elementType = computed(() =>
  props.tone === 'error'
    ? 'error'
    : props.tone === 'warning'
      ? 'warning'
      : props.tone === 'success'
        ? 'success'
        : 'info',
);
</script>

<template>
  <ElAlert
    class="inline-notice"
    :title="title"
    :type="elementType"
    :closable="false"
    show-icon
    :role="tone === 'error' ? 'alert' : 'status'"
  >
    <slot />
  </ElAlert>
</template>

<style scoped>
.inline-notice {
  align-items: flex-start;
  padding: var(--space-16);
  border-radius: var(--radius-control);
  overflow-wrap: anywhere;
}
.inline-notice :deep(.el-alert__title) {
  font-size: 16px;
  font-weight: 600;
}
.inline-notice :deep(.el-alert__description) {
  font-size: 14px;
  line-height: 1.6;
}
</style>
