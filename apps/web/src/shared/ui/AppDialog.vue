<script setup>
import { ElDialog } from 'element-plus';
import 'element-plus/theme-chalk/el-dialog.css';

/** Element Plus 管理焦点陷阱、Escape 和焦点恢复，页面只维护显式开关。 */
defineProps({ open: { type: Boolean, default: false }, title: { type: String, required: true } });
const emit = defineEmits(['close']);

/**
 * 将组件库关闭动作转换为业务组件事件，避免页面依赖库内部状态。
 * @param {boolean} open 对话框下一状态。
 */
function updateOpen(open) {
  if (!open) emit('close');
}
</script>

<template>
  <ElDialog
    :model-value="open"
    :title="title"
    width="min(520px, calc(100% - 32px))"
    :close-on-click-modal="false"
    :destroy-on-close="true"
    @update:model-value="updateOpen"
  >
    <slot />
  </ElDialog>
</template>
