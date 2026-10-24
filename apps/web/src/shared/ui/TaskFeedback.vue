<script setup>
import InlineNotice from './InlineNotice.vue';
import { nextTick, ref, watch } from 'vue';
const props = defineProps({
  error: { type: String, default: '' },
  notice: { type: String, default: '' },
});
const errorTarget = ref(/** @type {HTMLElement|null} */ (null));
/** 新提交错误渲染后聚焦持久文字，不清空原表单输入。 */
watch(
  () => props.error,
  async (value) => {
    if (value) {
      await nextTick();
      errorTarget.value?.focus();
    }
  },
);
</script>
<template>
  <div v-if="error" ref="errorTarget" tabindex="-1">
    <InlineNotice tone="error" title="操作未完成">{{ error }}</InlineNotice>
  </div>
  <InlineNotice v-if="notice" tone="success" title="操作反馈">{{ notice }}</InlineNotice>
</template>
