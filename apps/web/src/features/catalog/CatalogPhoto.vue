<script setup>
import { computed } from 'vue';
import AuthenticatedImage from '@/shared/ui/AuthenticatedImage.vue';
import { demoPhotoIndex } from './photo.js';
const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  simulation: Boolean,
});
const index = computed(() => demoPhotoIndex(props.simulation, props.src));
</script>
<template>
  <span
    v-if="index !== null"
    class="catalog-demo-photo"
    role="img"
    :aria-label="alt + '的 AI 演示配图，非实拍'"
    :style="{
      backgroundPosition: `${((index % 4) * 100) / 3}% ${(Math.floor(index / 4) * 100) / 3}%`,
    }"
  />
  <AuthenticatedImage v-else :src="src" :alt="alt" />
</template>
<style scoped>
/* 只对旧示例编号显示合成拼图；其他图片沿用认证和取消边界。 */
.catalog-demo-photo {
  display: block;
  width: 100%;
  height: 100%;
  background-image: url('/brand/market-demo-photos.png');
  background-size: 400% 400%;
  background-repeat: no-repeat;
  border-radius: inherit;
}
</style>
