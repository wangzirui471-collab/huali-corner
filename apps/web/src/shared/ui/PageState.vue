<script setup>
/** 页面六类状态的统一容器；内容由页面插槽呈现，失败保留重试出口。 */
defineProps({
  state: { type: String, required: true },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
});
</script>

<template>
  <section
    class="page-state"
    :data-state="state"
    :aria-busy="state === 'loading' || state === 'submitting' || undefined"
    :role="state === 'error' ? 'alert' : undefined"
  >
    <template v-if="state === 'content'"><slot /></template>
    <template v-else>
      <h3>{{ title }}</h3>
      <p v-if="description">{{ description }}</p>
      <div v-if="state === 'loading'" class="page-state__skeleton" aria-hidden="true"></div>
      <slot name="action" />
    </template>
  </section>
</template>

<style scoped>
.page-state {
  padding: var(--space-24);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  overflow-wrap: anywhere;
}
.page-state h3 {
  margin-bottom: var(--space-8);
  font-size: 18px;
}
.page-state p {
  color: var(--color-text-secondary);
}
.page-state[data-state='error'] h3,
.page-state[data-state='forbidden'] h3 {
  color: var(--color-danger);
}
.page-state__skeleton {
  height: 64px;
  background: var(--color-canvas);
  border-radius: var(--radius-control);
}
</style>
