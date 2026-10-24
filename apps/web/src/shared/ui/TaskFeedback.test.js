import { it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import TaskFeedback from './TaskFeedback.vue';
/** 提交失败自动聚焦持久反馈，让键盘用户无需从页尾寻找错误。 */
it('新错误出现时将焦点移到可见反馈', async () => {
  const wrapper = mount(TaskFeedback, { attachTo: document.body, props: { error: '' } });
  await wrapper.setProps({ error: '图片上传失败，输入已保留' });
  await flushPromises();
  expect(document.activeElement?.textContent).toContain('图片上传失败');
  expect(document.activeElement?.getAttribute('tabindex')).toBe('-1');
  wrapper.unmount();
});
