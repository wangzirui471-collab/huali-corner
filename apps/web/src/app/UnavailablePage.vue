<script setup>
import PageState from '@/shared/ui/PageState.vue';
</script>

<template>
  <main class="unavailable-page">
    <PageState state="empty" title="页面尚未开放" description="请使用当前已发布的华立转角入口。" />
  </main>
</template>

<style scoped>
.unavailable-page {
  max-width: var(--content-width);
  margin: var(--space-48) auto;
  padding: var(--space-16);
}
</style>
