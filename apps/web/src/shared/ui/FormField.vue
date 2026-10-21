<script setup>
import { computed, useId } from 'vue';

/** 统一标签、帮助和错误关系；插槽通过 slot props 关联真实输入控件。 */
const props = defineProps({
  id: { type: String, default: undefined },
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  required: { type: Boolean, default: false },
});
const generatedId = useId();
const id = computed(() => props.id || generatedId);
const describedBy = computed(() =>
  props.error || props.hint ? `${id.value}-description` : undefined,
);
</script>

<template>
  <div class="form-field" :data-invalid="Boolean(error)">
    <label :for="id" class="form-field__label">{{ label }}{{ required ? '（必填）' : '' }}</label>
    <slot v-bind="{ id, describedBy, invalid: Boolean(error) }" />
    <p
      v-if="error || hint"
      :id="describedBy"
      class="form-field__description"
      :role="error ? 'alert' : undefined"
    >
      {{ error || hint }}
    </p>
  </div>
</template>

<style scoped>
.form-field {
  display: grid;
  gap: var(--space-8);
  width: 100%;
  min-width: 0;
}
.form-field__label {
  font-weight: 600;
}
.form-field :deep(input),
.form-field :deep(textarea),
.form-field :deep(select) {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: var(--space-8) var(--space-12);
  border: 1px solid var(--color-control-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 16px;
}
.form-field[data-invalid='true'] :deep(input) {
  border-color: var(--color-danger);
}
/* 库组件已提供外层边框，内部 input 不再叠加边框。 */
.form-field :deep(.el-input__inner) {
  min-height: 42px;
  padding: 0;
  border: 0;
  background: transparent;
}
.form-field__description {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}
.form-field[data-invalid='true'] .form-field__description {
  color: var(--color-danger);
}
</style>
