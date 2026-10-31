<script setup>
/**
 * 逛逛页主视觉岛：Element Plus 轮播 + 一排频道。
 * 只做呈现与手势，跳转和筛选继续交给原生 data-action 事件层，避免两套业务逻辑。
 */
import { onBeforeUnmount, ref } from 'vue';
import { ElCarousel, ElCarouselItem } from 'element-plus';

const props = defineProps({
  slides: { type: Array, default: () => [] },
  channels: { type: Array, default: () => [] }
});

// el-carousel 需要显式高度，窄屏换一次断点就重算，避免文字被裁。
function heroHeight(){ return window.innerWidth < 620 ? '252px' : '244px'; }
const height = ref(heroHeight());
let compact = window.innerWidth < 620;
const onResize = () => {
  if ((window.innerWidth < 620) === compact) return;
  compact = !compact;
  height.value = heroHeight();
};
window.addEventListener('resize', onResize);
onBeforeUnmount(() => window.removeEventListener('resize', onResize));
</script>

<template>
  <div class="hc-root">
    <el-carousel class="hc-hero" :interval="7000" :height="height" arrow="hover" :pause-on-hover="true">
      <el-carousel-item v-for="slide in props.slides" :key="slide.key">
        <button
          class="hc-slide"
          :class="'hc-tone-' + slide.tone"
          :data-action="slide.link.action"
          :data-value="slide.link.value"
          :data-q="slide.link.q"
          :data-go="slide.link.go"
          :aria-label="slide.title + '，' + slide.cta"
        >
          <span class="hc-copy">
            <span class="hc-eyebrow">{{ slide.eyebrow }}</span>
            <strong class="hc-title">{{ slide.title }}</strong>
            <span class="hc-desc">{{ slide.description }}</span>
            <span class="hc-cta">{{ slide.cta }}<span class="hc-cta-icon" v-html="slide.arrow"></span></span>
          </span>
          <span class="hc-art" v-html="slide.art"></span>
        </button>
      </el-carousel-item>
    </el-carousel>
    <nav class="hc-cats" aria-label="商品频道">
      <button
        v-for="channel in props.channels"
        :key="channel.key"
        class="hc-cat"
        :class="{ active: channel.active }"
        :data-action="channel.action"
        :data-value="channel.value"
        :data-q="channel.q"
        :data-go="channel.go"
        :aria-pressed="channel.active ? 'true' : 'false'"
      >
        <span class="hc-cat-icon" v-html="channel.icon"></span><span>{{ channel.label }}</span>
      </button>
    </nav>
  </div>
</template>

<style>
/* 只覆盖 Element Plus 自带的轮播外观，页面配色统一由 home.css 负责。 */
.hc-root .el-carousel__container { height: 244px; }
.hc-root .el-carousel__indicators--horizontal { left: 28px; right: auto; transform: none; bottom: 14px; }
.hc-root .el-carousel__button { width: 16px; height: 4px; border-radius: 4px; background: #14635533; opacity: 1; }
.hc-root .el-carousel__indicator--horizontal.is-active .el-carousel__button { background: #0f7b63; }
.hc-root .el-carousel__arrow { background: #ffffffcc; color: #146355; border: 1px solid #d7e8e2; box-shadow: none; }
.hc-root .el-carousel__arrow:hover { background: #fff; color: #0f7b63; }
@media (max-width: 620px){
  .hc-root .el-carousel__container { height: 252px; }
  .hc-root .el-carousel__indicators--horizontal { left: 16px; }
}
</style>
