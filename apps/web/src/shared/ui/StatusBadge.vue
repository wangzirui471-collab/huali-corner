<script setup>
import { computed } from 'vue';
import { ElTag } from 'element-plus';
import 'element-plus/theme-chalk/el-tag.css';

/** Element Plus 标签适配；文字与颜色共同表达状态，不只依靠颜色。 */
const props = defineProps({
  tone: { type: String, default: 'neutral' },
  label: { type: String, required: true },
});
const elementType = computed(() =>
  props.tone === 'success'
    ? 'success'
    : props.tone === 'warning'
      ? 'warning'
      : props.tone === 'danger'
        ? 'danger'
        : 'info',
);
</script>

<template>
  <ElTag class="status-badge" :type="elementType" effect="plain" :data-tone="tone">{{
    label
  }}</ElTag>
</template>

<style scoped>
.status-badge {
  height: auto;
  padding: var(--space-4) var(--space-8);
  border-radius: var(--radius-control);
  font-size: 13px;
  white-space: normal;
}
</style>
