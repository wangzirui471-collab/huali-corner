<script setup>
import { ref } from 'vue';

/** 汇总提交错误并提供字段入口；字段旁仍保留具体错误说明。 */
defineProps({
  errors: {
    type: /** @type {import('vue').PropType<Array<{ fieldId: string, label: string, message: string }>>} */ (
      Array
    ),
    required: true,
  },
});
const container = ref(/** @type {HTMLElement | null} */ (null));

/** 仅在提交失败后由表单调用，使键盘和读屏用户知道有哪些内容需要修改。 */
function focus() {
  container.value?.focus();
}

/** 激活错误链接后把焦点交给输入框，浏览器同时滚动到对应字段。 */
function focusField(/** @type {string} */ fieldId) {
  globalThis.document.getElementById(fieldId)?.focus();
}

defineExpose({ focus });
</script>

<template>
  <section ref="container" class="error-summary" tabindex="-1" aria-label="请检查以下内容">
    <h3>请检查以下 {{ errors.length }} 项内容</h3>
    <ul>
      <li v-for="error in errors" :key="error.fieldId">
        <a :href="`#${error.fieldId}`" @click.prevent="focusField(error.fieldId)">
          {{ error.label }}：{{ error.message }}
        </a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.error-summary {
  margin-bottom: var(--space-20);
  padding: var(--space-16);
  border: 2px solid var(--color-danger);
  border-radius: var(--radius-control);
  scroll-margin-block: var(--space-24);
}
.error-summary h3 {
  margin-bottom: var(--space-8);
  font-size: 18px;
}
.error-summary ul {
  margin: 0;
  padding-left: var(--space-24);
}
.error-summary a {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  color: var(--color-danger);
  overflow-wrap: anywhere;
}
.error-summary:focus {
  outline: 3px solid var(--color-focus);
  outline-offset: 3px;
}
</style>
