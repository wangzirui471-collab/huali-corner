import { createApp } from "vue";
import "@/shared/design-tokens/tokens.css";
import "@/shared/ui/element-plus.css";
import "@/app/base.css";
import { installPreviewApi } from "./preview-api.js";

// 先替换网络，再动态加载真实路由与页面；所有演示请求都留在本机内存。
installPreviewApi();
const [{ session }, { router }, { default: AppliedReview }] = await Promise.all(
  [
    import("@/shared/legacy/session.js"),
    import("@/app/router.js"),
    import("./AppliedReview.vue"),
  ],
);
session.token = "ui-preview-synthetic-only";
session.me = { id: 7, nickname: "预览同学", role: "user", score: 100 };
session.ready = false;
createApp(AppliedReview).use(router).mount("#app");
