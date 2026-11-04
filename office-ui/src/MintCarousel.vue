<script setup>
import { inject, ref } from 'vue';

defineProps({ slides: { type: Array, required: true } });
const locale = inject('mintLocale');
const index = ref(0);

/** 只让当前专题的跳转获得焦点和响应点击。 */
function selectSlide(next) {
  index.value = next;
}
</script>

<template>
  <el-config-provider :locale="locale">
    <el-carousel class="mint-carousel" indicator-position="outside" arrow="always" trigger="click"
      :autoplay="false" @change="selectSlide">
      <el-carousel-item v-for="(slide, i) in slides" :key="slide.title">
        <div class="mint-slide" :data-art="slide.art" :inert="i !== index">
          <div class="mint-slide-photo" aria-hidden="true"></div>
          <div class="mint-slide-copy">
            <small>{{ slide.eyebrow }}</small>
            <h2>{{ slide.title }}</h2>
            <p>{{ slide.description }}</p>
            <button type="button" :data-go="slide.go" class="mint-topic-link">{{ slide.cta }} <span aria-hidden="true">↗</span></button>
          </div>
        </div>
      </el-carousel-item>
    </el-carousel>
  </el-config-provider>
</template>
