<script setup>
import { computed } from 'vue';
import { ElButton } from 'element-plus';
import 'element-plus/theme-chalk/el-button.css';

/** Element Plus 按钮适配：统一业务变体、暖黄主操作与提交中行为。 */
const props = defineProps({
  variant: { type: String, default: 'primary' },
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
});
const elementType = computed(() =>
  props.variant === 'primary' ? 'primary' : props.variant === 'danger' ? 'danger' : undefined,
);
const nativeType = computed(() =>
  props.type === 'submit' ? 'submit' : props.type === 'reset' ? 'reset' : 'button',
);
</script>

<template>
  <ElButton
    class="app-button"
    :data-variant="variant"
    :type="elementType"
    :text="variant === 'quiet'"
    :native-type="nativeType"
    :disabled="disabled || loading"
    :loading="loading"
    :aria-busy="loading || undefined"
  >
    <slot />
  </ElButton>
</template>

<style scoped>
.app-button {
  min-width: 88px;
  min-height: 44px;
  height: auto;
  padding: var(--space-8) var(--space-16);
  border-radius: var(--radius-control);
  font-weight: 600;
  white-space: normal;
  overflow-wrap: anywhere;
}
.app-button + .app-button {
  margin-left: 0;
}
.app-button[data-variant='primary'] {
  --el-button-bg-color: var(--color-action);
  --el-button-text-color: var(--color-action-ink);
  --el-button-border-color: var(--color-action);
  --el-button-hover-bg-color: var(--color-action-hover);
  --el-button-hover-text-color: var(--color-action-ink);
  --el-button-hover-border-color: var(--color-action-hover);
  --el-button-active-bg-color: var(--color-action-hover);
  --el-button-active-border-color: var(--color-action-hover);
  --el-button-active-text-color: var(--color-action-ink);
  --el-button-disabled-bg-color: var(--color-action);
  --el-button-disabled-text-color: var(--color-action-ink);
  --el-button-disabled-border-color: var(--color-control-border);
}
.app-button[data-variant='quiet'] {
  color: var(--color-link);
}
.app-button:disabled {
  border-style: dashed;
}
.app-button:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 3px;
}
</style>
