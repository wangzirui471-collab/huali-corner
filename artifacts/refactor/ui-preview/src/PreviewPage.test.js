import { mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import PreviewPage from "./PreviewPage.vue";

const mounted = [];
/** 预览组件卸载时清理轮播和合成计时器。 */
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.useRealTimers();
});

/** 用户主动暂停后，等待多个轮播周期仍停留在当前专题。 */
it("允许暂停独立专题轮播", async () => {
  vi.useFakeTimers();
  const wrapper = mount(PreviewPage);
  mounted.push(wrapper);
  const panel = wrapper.get('[aria-label="书籍与生活专题"]');
  const title = panel.get("h2").text();
  await panel
    .get('button[aria-label="暂停书籍与生活专题轮播"]')
    .trigger("click");
  await vi.advanceTimersByTimeAsync(16000);
  expect(panel.get("h2").text()).toBe(title);
  expect(
    panel.find('button[aria-label="继续书籍与生活专题轮播"]').exists(),
  ).toBe(true);
});

/** 搜索返回可见的合成商品，不发送业务请求。 */
it("按输入搜索并能清除条件", async () => {
  const wrapper = mount(PreviewPage);
  mounted.push(wrapper);
  await wrapper.get('input[type="search"]').setValue("台灯");
  await wrapper.get('form[role="search"]').trigger("submit");
  expect(wrapper.findAll(".product-card")).toHaveLength(1);
  expect(wrapper.get(".product-card").text()).toContain("台灯");
  await wrapper.get('button[aria-label="清除搜索条件"]').trigger("click");
  expect(wrapper.findAll(".product-card").length).toBeGreaterThan(1);
});

/** 收藏是独立按钮，点击只更新当前预览中的状态与可读反馈。 */
it("独立收藏按钮反馈状态", async () => {
  const wrapper = mount(PreviewPage);
  mounted.push(wrapper);
  const button = wrapper.findAll(".favorite-button")[0];
  expect(button.attributes("aria-pressed")).toBe("false");
  await button.trigger("click");
  expect(button.attributes("aria-pressed")).toBe("true");
  expect(wrapper.get('[role="status"]').text()).toContain("已收藏");
});
