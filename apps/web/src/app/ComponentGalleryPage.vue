<script setup>
import { computed, nextTick, reactive, ref, useId, watch } from 'vue';
import { ElForm, ElFormItem, ElInput } from 'element-plus';
import 'element-plus/theme-chalk/el-form.css';
import 'element-plus/theme-chalk/el-form-item.css';
import 'element-plus/theme-chalk/el-input.css';
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import FormField from '@/shared/ui/FormField.vue';
import FormErrorSummary from '@/shared/ui/FormErrorSummary.vue';
import InlineNotice from '@/shared/ui/InlineNotice.vue';
import PageState from '@/shared/ui/PageState.vue';
import StatusBadge from '@/shared/ui/StatusBadge.vue';

/** 开发样板使用纯本地状态，操作不产生真实商品、账号或订单。 */
const dialogOpen = ref(false);
const form = reactive({ title: '高等数学教材', location: '' });
const formRef = ref(/** @type {import('element-plus').FormInstance | undefined} */ (undefined));
const summaryRef = ref(
  /** @type {InstanceType<typeof FormErrorSummary> | undefined} */ (undefined),
);
const formId = useId();
const fields =
  /** @type {Array<{ key: 'title' | 'location', label: string, id: string, hint: string }>} */ ([
    {
      key: 'title',
      label: '商品标题',
      id: `${formId}-title`,
      hint: '写清商品名称，方便同学搜索。',
    },
    {
      key: 'location',
      label: '交付地点',
      id: `${formId}-location`,
      hint: '填写校内公共地点，避免填写宿舍房间号。',
    },
  ]);
const errors = ref(/** @type {Record<string, string>} */ ({}));
const errorItems = computed(() =>
  fields
    .filter((field) => errors.value[field.key])
    .map((field) => ({
      fieldId: field.id,
      label: field.label,
      message: errors.value[field.key] || '',
    })),
);
const rules = {
  title: [{ required: true, whitespace: true, message: '请填写商品标题。', trigger: 'submit' }],
  location: [{ required: true, whitespace: true, message: '请填写交付地点。', trigger: 'submit' }],
};
const confirmed = ref(false);
const previewReady = ref(false);
// 一旦用户继续编辑，先前的通过结果不再代表当前输入。
watch(form, () => {
  previewReady.value = false;
});
const states = [
  { state: 'loading', title: '正在加载商品', description: '请稍候，商品列表正在准备。' },
  { state: 'empty', title: '还没有相关商品', description: '换个关键词，或者发布一条求购。' },
  { state: 'error', title: '加载失败', description: '网络暂时不可用，已填写的内容会保留。' },
  { state: 'forbidden', title: '暂时无法发布', description: '请查看账号状态，或在客服中心申诉。' },
  { state: 'submitting', title: '正在提交', description: '请稍候，避免重复提交相同操作。' },
];

/** 只改变样板提示，用于检查对话框关闭和键盘焦点恢复。 */
function confirmPreview() {
  confirmed.value = true;
  dialogOpen.value = false;
}

/** 使用控件库校验整个表单；失败保留输入，并在更新 DOM 后聚焦错误汇总。 */
async function submitPreview() {
  if (!formRef.value) return;
  errors.value = {};
  previewReady.value = false;
  try {
    previewReady.value = await formRef.value.validate();
  } catch (invalidFields) {
    const failures = /** @type {Record<string, Array<{ message?: string }>>} */ (invalidFields);
    for (const field of fields) {
      const message = failures[field.key]?.[0]?.message;
      if (message) errors.value[field.key] = message;
    }
    await nextTick();
    summaryRef.value?.focus();
  }
}
</script>

<template>
  <a class="skip-link" href="#main">跳至组件内容</a>
  <header class="gallery-header">
    <div class="gallery-header__inner">
      <img :src="'/brand/logo-lockup.svg'" alt="华立转角" width="188" height="60" />
      <span>设计与交互样板 · 隔离预览</span>
    </div>
  </header>
  <main id="main" class="gallery">
    <div class="gallery-intro">
      <p class="gallery-eyebrow">华立转角 / 共用组件</p>
      <h1>让每一次操作都清楚、顺手</h1>
      <p>统一按钮、表单与反馈，供后续页面复用。这里的操作只用于交互预览。</p>
    </div>

    <section class="gallery-section" aria-labelledby="buttons-title">
      <h2 id="buttons-title">操作按钮</h2>
      <p>暖黄用于主要操作；危险操作清楚说明后果。使用 Tab 可检查焦点。</p>
      <div class="gallery-row">
        <AppButton @click="dialogOpen = true">发布商品</AppButton>
        <AppButton variant="secondary">继续编辑</AppButton>
        <AppButton variant="quiet">查看详情</AppButton>
        <AppButton variant="danger" @click="dialogOpen = true">确认下架</AppButton>
        <AppButton disabled>暂不可用</AppButton>
        <AppButton loading>保存草稿</AppButton>
      </div>
      <div class="gallery-row">
        <AppButton variant="secondary"
          >这是一条很长的操作文案，用来检查手机换行后仍可完整阅读</AppButton
        >
      </div>
    </section>

    <section class="gallery-section" aria-labelledby="form-title">
      <h2 id="form-title">填写与校验</h2>
      <p>先填写，再检查。错误会在提交后集中列出，已填内容会保留。</p>
      <ElForm
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submitPreview"
      >
        <FormErrorSummary v-if="errorItems.length" ref="summaryRef" :errors="errorItems" />
        <div class="gallery-grid">
          <ElFormItem v-for="item in fields" :key="item.key" :prop="item.key" :show-message="false">
            <FormField
              :id="item.id"
              v-slot="field"
              :label="item.label"
              :hint="item.hint"
              :error="errors[item.key]"
              required
            >
              <ElInput
                :id="field.id"
                v-model="form[item.key]"
                :aria-invalid="field.invalid || undefined"
                :aria-describedby="field.describedBy"
                :aria-required="true"
              />
            </FormField>
          </ElFormItem>
        </div>
        <AppButton type="submit">检查填写内容</AppButton>
        <InlineNotice
          v-if="previewReady"
          class="gallery-form-result"
          tone="success"
          title="填写检查通过"
        >
          尚未发布商品；这里仅演示本地表单校验，填写内容仍保留。
        </InlineNotice>
      </ElForm>
    </section>

    <section class="gallery-section" aria-labelledby="feedback-title">
      <h2 id="feedback-title">状态与反馈</h2>
      <div class="gallery-row">
        <StatusBadge label="在售" tone="success" />
        <StatusBadge label="等待付款" tone="warning" />
        <StatusBadge label="已下架" />
        <StatusBadge label="需要处理" tone="danger" />
      </div>
      <div class="gallery-grid">
        <InlineNotice tone="warning" title="模拟交易说明"
          >付款和退款用于流程演示，请按线下约定交付。</InlineNotice
        >
        <InlineNotice tone="error" title="保存失败，内容已保留"
          >请检查网络后重试；不要重复创建相同订单。</InlineNotice
        >
      </div>
      <InlineNotice v-if="confirmed" tone="success" title="已完成样板操作"
        >对话框已关闭，焦点回到触发按钮。</InlineNotice
      >
    </section>

    <section class="gallery-section" aria-labelledby="states-title">
      <h2 id="states-title">页面六类状态</h2>
      <div class="gallery-grid">
        <PageState state="content">
          <StatusBadge label="内容已就绪" tone="success" />
          <h3 class="gallery-content-title">高等数学教材</h3>
          <p>有少量课堂笔记，适合新学期继续使用。</p>
          <strong class="gallery-price">¥ 18.00</strong>
        </PageState>
        <PageState v-for="item in states" :key="item.state" v-bind="item">
          <template v-if="item.state === 'error'" #action>
            <AppButton variant="secondary" @click="dialogOpen = true">重试</AppButton>
          </template>
        </PageState>
      </div>
    </section>
    <AppDialog :open="dialogOpen" title="操作确认样板" @close="dialogOpen = false">
      <p>此操作只验证弹窗、键盘与焦点行为，不修改业务数据。</p>
      <div class="gallery-row">
        <AppButton @click="confirmPreview">确认预览</AppButton>
        <AppButton variant="secondary" @click="dialogOpen = false">取消</AppButton>
      </div>
    </AppDialog>
  </main>
</template>

<style scoped>
.skip-link {
  position: fixed;
  top: var(--space-8);
  left: var(--space-16);
  z-index: var(--layer-overlay);
  padding: var(--space-8);
  background: var(--color-surface);
  transform: translateY(-200%);
}
.skip-link:focus {
  transform: translateY(0);
}
.gallery-header {
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}
.gallery-header__inner,
.gallery {
  max-width: var(--content-width);
  margin: 0 auto;
  padding: var(--space-16) var(--space-24);
}
.gallery-header__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-16);
}
.gallery-header span,
.gallery-intro > p,
.gallery-section > p {
  color: var(--color-text-secondary);
}
.gallery-intro {
  padding: var(--space-32) 0 var(--space-16);
}
.gallery-eyebrow {
  margin-bottom: var(--space-8);
  color: var(--color-link);
  font-weight: 600;
}
.gallery h1 {
  margin-bottom: var(--space-16);
  font-size: clamp(26px, 4vw, 32px);
}
.gallery-section {
  margin-bottom: var(--space-24);
  padding: var(--space-24);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}
.gallery-section h2 {
  font-size: 22px;
  margin-bottom: var(--space-12);
}
.gallery-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-12);
  margin-bottom: var(--space-16);
}
.gallery-row > * {
  max-width: 100%;
}
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-16);
  margin-bottom: var(--space-16);
}
.gallery-grid :deep(.el-form-item) {
  margin-bottom: 0;
}
.gallery-content-title {
  margin-top: var(--space-16);
}
.gallery-form-result {
  margin-top: var(--space-16);
}
.gallery-price {
  color: var(--color-price);
}
@media (max-width: 640px) {
  .gallery,
  .gallery-header__inner {
    padding: var(--space-12);
  }
  .gallery-header__inner {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--space-4);
  }
  .gallery-section {
    padding: var(--space-16);
  }
  .gallery-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
