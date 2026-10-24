import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeAll, expect, it } from "vitest";
import { installPreviewApi } from "./preview-api.js";

let CommunityPage, OrdersPage;
const mounted = [];
/** 先安装本机合成接口，再导入会捕获请求客户端的业务组件。 */
beforeAll(async () => {
  installPreviewApi();
  const { session } = await import("@/shared/legacy/session.js");
  session.token = "ui-preview-synthetic-only";
  session.me = { id: 7, nickname: "预览同学", role: "user" };
  CommunityPage = (await import("@/features/community/CommunityPage.vue"))
    .default;
  OrdersPage = (await import("@/features/trade/OrdersPage.vue")).default;
}, 30000);
/** 卸载查询与页面作用域，避免下一项测试继承页面状态。 */
afterEach(() => mounted.splice(0).forEach((wrapper) => wrapper.unmount()));
/** 使用真实路由上下文挂载当前候选页面。 */
async function open(Component, path) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: Component }],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(Component, { global: { plugins: [router] } });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}
/** 先阅读后编辑；展开、收起发布区域时保留尚未提交的草稿。 */
it("社区发布按需展开并保留草稿", async () => {
  const wrapper = await open(CommunityPage, "/community");
  const trigger = wrapper.get('button[aria-controls="review-compose"]');
  expect(trigger.attributes("aria-expanded")).toBe("false");
  await trigger.trigger("click");
  await wrapper.get("#review-title").setValue("尚未发布的内容");
  await trigger.trigger("click");
  await trigger.trigger("click");
  expect(wrapper.get("#review-title").element.value).toBe("尚未发布的内容");
});

/** 预览拒绝发送时，错误保持可读，用户填写的内容不会被当成成功而清空。 */
it("预览发布失败仍保留原输入", async () => {
  const wrapper = await open(CommunityPage, "/community");
  await wrapper.get('button[aria-controls="review-compose"]').trigger("click");
  await wrapper.get("#review-title").setValue("草稿标题");
  await wrapper.get("#review-compose textarea").setValue("尚未发送的正文");
  await wrapper.get("#review-compose").trigger("submit");
  await flushPromises();
  expect(wrapper.get("#review-title").element.value).toBe("草稿标题");
  expect(wrapper.get("#review-compose textarea").element.value).toBe(
    "尚未发送的正文",
  );
  expect(wrapper.text()).toContain("预览");
  expect(wrapper.find('[role="alert"]').exists()).toBe(true);
});
/** 待付款筛选只显示该状态的订单，不把卖家待收货记录混入。 */
it("订单状态入口能直接定位待处理订单", async () => {
  const wrapper = await open(OrdersPage, "/orders");
  await wrapper
    .get('button[data-order-filter="awaiting_payment"]')
    .trigger("click");
  expect(wrapper.findAll(".review-order")).toHaveLength(1);
  expect(wrapper.get(".review-order").text()).toContain("#601");
  expect(wrapper.get(".review-order").text()).toContain("待付款");
});
