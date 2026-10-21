/** 通过页面表单和可见 DOM 验证交互，不访问组件内部状态。 */
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, expect, it } from 'vitest';
import ComponentGalleryPage from './ComponentGalleryPage.vue';

/** 每个场景结束后移除真实挂载点，避免焦点影响后续用例。 */
afterEach(() => {
  globalThis.document.body.replaceChildren();
});

/** 无效提交应保留输入，将焦点移到错误汇总，并允许直达需要修改的字段。 */
it('提交后可用错误汇总定位字段，并保留已经填写的标题', async () => {
  const page = mount(ComponentGalleryPage, { attachTo: globalThis.document.body });
  const title = page.get('input');
  await title.setValue('高等数学（第七版）');
  await page.get('form').trigger('submit');
  await flushPromises();
  await expect.poll(() => page.find('[aria-label="请检查以下内容"]').exists()).toBe(true);
  const summary = page.get('[aria-label="请检查以下内容"]');
  expect(summary.text()).toContain('交付地点');
  expect(globalThis.document.activeElement).toBe(summary.element);
  expect(title.element.value).toBe('高等数学（第七版）');

  const errorLink = summary.get('a');
  await errorLink.trigger('click');
  const destination = page.get(errorLink.attributes('href') || '#missing-field');
  expect(globalThis.document.activeElement).toBe(destination.element);
  expect(destination.attributes('aria-invalid')).toBe('true');
  page.unmount();
});

/** 修正字段后应清除错误并给出持久反馈；继续编辑时不能保留过期的通过提示。 */
it('修正表单后显示检查结果，继续编辑时撤销旧结果', async () => {
  const page = mount(ComponentGalleryPage, { attachTo: globalThis.document.body });
  await page.get('form').trigger('submit');
  await expect.poll(() => page.find('[aria-label="请检查以下内容"]').exists()).toBe(true);

  const location = page.get('input[id$="-location"]');
  await location.setValue('图书馆一楼公共大厅');
  await page.get('form').trigger('submit');
  await expect.poll(() => page.find('form [role="status"]').exists()).toBe(true);
  expect(page.find('[aria-label="请检查以下内容"]').exists()).toBe(false);
  expect(page.get('form [role="status"]').text()).toContain('填写检查通过');
  expect(page.get('form [role="status"]').text()).toContain('尚未发布商品');
  expect(location.attributes('aria-invalid')).toBeUndefined();

  await location.setValue('');
  expect(page.find('form [role="status"]').exists()).toBe(false);
  page.unmount();
});
