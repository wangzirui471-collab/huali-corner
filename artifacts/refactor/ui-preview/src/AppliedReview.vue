<script setup>
import { RouterLink, RouterView } from "vue-router";
import "./page-review.css";
</script>
<template>
  <div class="applied-review-note">
    界面调整预览 · 社区 / 论坛 / 消息 / 订单 · 演示数据，发送及交易操作暂不可用
    <nav aria-label="界面方案切换">
      <RouterLink to="/community">社区动态</RouterLink
      ><RouterLink to="/forum">论坛话题</RouterLink
      ><RouterLink to="/messages/9">消息会话</RouterLink
      ><RouterLink to="/orders">订单状态</RouterLink>
    </nav>
  </div>
  <RouterView />
</template>
<style>
/* 仅评审宿主显示说明条，正式业务构建不包含该文字或合成接口。 */
.applied-review-note {
  background: #eee8f5;
  color: #68509c;
  text-align: center;
  padding: 6px 16px;
  font-size: 12px;
}
.applied-review-note nav {
  display: inline-flex;
  gap: 20px;
  flex-wrap: wrap;
  margin-left: 24px;
}
.applied-review-note a {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  color: #493759;
  text-decoration: none;
  border-bottom: 2px solid transparent;
}
.applied-review-note a.router-link-active {
  border-bottom-color: #68509c;
  font-weight: 700;
}
@media (max-width: 767px) {
  .applied-review-note nav {
    margin-left: 0;
    justify-content: center;
    gap: 16px;
    display: flex;
  }
  .applied-review-note a {
    min-height: 44px;
  }
}
</style>
