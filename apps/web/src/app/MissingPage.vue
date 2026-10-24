<script setup>
import { RouterLink } from 'vue-router';
import PageState from '@/shared/ui/PageState.vue';
</script>
<template>
  <PageState
    state="empty"
    title="没有找到这个页面"
    description="地址可能已经变更，可以回到校园集市继续逛逛。"
    ><template #action><RouterLink to="/">返回集市</RouterLink></template></PageState
  >
</template>
