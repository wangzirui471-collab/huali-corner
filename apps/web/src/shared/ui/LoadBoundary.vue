<script setup>
import PageState from './PageState.vue';
import AppButton from './AppButton.vue';
defineProps({
  loading: Boolean,
  error: { type: String, default: '' },
  forbidden: Boolean,
  empty: Boolean,
});
defineEmits(['retry']);
</script>
<template>
  <PageState
    v-if="error"
    :state="forbidden ? 'forbidden' : 'error'"
    :title="forbidden ? '暂时无权查看' : '读取未完成'"
    :description="error"
    ><template #action
      ><AppButton variant="secondary" @click="$emit('retry')">重试</AppButton></template
    ></PageState
  ><PageState
    v-else-if="loading"
    state="loading"
    title="正在加载"
    description="请稍候…"
  /><PageState
    v-else-if="empty"
    state="empty"
    title="这里暂时没有内容"
    description="换个筛选条件，或稍后再来看看。"
  /><slot v-else />
</template>
