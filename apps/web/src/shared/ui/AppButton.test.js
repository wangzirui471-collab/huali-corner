/** 基础控件的行为合同：防止重复提交，并保持原生键盘及表单语义。 */
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import AppButton from './AppButton.vue';
import FormField from './FormField.vue';
import { h } from 'vue';

describe('基础控件', () => {
  /** loading 不仅改变外观，还必须阻止重复 click 事件。 */
  it('提交中保留名称并阻止重复点击', async () => {
    const wrapper = mount(AppButton, { props: { loading: true }, slots: { default: '发布商品' } });
    expect(wrapper.attributes('aria-busy')).toBe('true');
    expect(wrapper.attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('发布商品');
    await wrapper.trigger('click');
    expect(wrapper.emitted('click')).toBeUndefined();
  });

  /** 按钮默认不提交表单；只有页面明确指定 submit 时才提交。 */
  it('默认按钮类型和危险状态语义正确', () => {
    const wrapper = mount(AppButton, {
      props: { variant: 'danger' },
      slots: { default: '确认下架' },
    });
    expect(wrapper.attributes('type')).toBe('button');
    expect(wrapper.attributes('data-variant')).toBe('danger');
  });

  /** 表单错误必须有可关联的稳定编号和文字，不能仅用红框表达。 */
  it('字段错误可通过编号关联并作为警告朗读', () => {
    const wrapper = mount(FormField, {
      props: { label: '商品标题', error: '请填写标题' },
      slots: {
        default: (field) => h('input', { id: field.id, 'aria-describedby': field.describedBy }),
      },
    });
    expect(wrapper.get('label').attributes('for')).toBeTruthy();
    expect(wrapper.get('[role="alert"]').text()).toBe('请填写标题');
    expect(wrapper.get('input').attributes('aria-describedby')).toBe(
      wrapper.get('[role="alert"]').attributes('id'),
    );
  });
});
