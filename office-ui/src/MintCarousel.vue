<script setup>
import { computed, inject, onMounted, onUnmounted, ref } from 'vue';

defineProps({ slides: { type: Array, required: true } });
const locale = inject('mintLocale');
const index = ref(0);
const enabled = ref(false);
const focused = ref(false);
const hidden = ref(document.hidden);
const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
const reduced = ref(preference.matches);
const playing = computed(() => enabled.value && !hidden.value && !focused.value && !reduced.value);

/** 同步浏览器的动态效果偏好，减少动态效果时关闭自动播放。 */
function syncPreference() {
  reduced.value = preference.matches;
  if (reduced.value) enabled.value = false;
}

/** 后台标签页停止轮播，返回时按用户选择继续。 */
function syncVisibility() {
  hidden.value = document.hidden;
}

/** 焦点仍在轮播内时保持暂停，方便键盘用户访问专题。 */
function updateFocus(event) {
  focused.value = event.currentTarget.contains(event.relatedTarget);
}

/** 只有当前专题的跳转能获得焦点和响应点击。 */
function selectSlide(next) {
  index.value = next;
}

/** 默认静止，用户可以按需开启或暂停播放。 */
function togglePlayback() {
  enabled.value = !enabled.value;
}

/** 随轮播组件注册页面事件。 */
onMounted(() => {
  preference.addEventListener('change', syncPreference);
  document.addEventListener('visibilitychange', syncVisibility);
});

/** 离开首页后清除监听，避免轮播影响其他页面。 */
onUnmounted(() => {
  preference.removeEventListener('change', syncPreference);
  document.removeEventListener('visibilitychange', syncVisibility);
});
</script>

<template>
  <el-config-provider :locale="locale">
    <div class="mint-carousel-frame">
      <div @focusin="focused = true" @focusout="updateFocus">
        <el-carousel class="mint-carousel" indicator-position="outside" arrow="always" trigger="click"
          :autoplay="playing" :interval="7500" :pause-on-hover="true" @change="selectSlide">
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
      </div>
      <button v-if="!reduced" type="button" class="mint-play" @click="togglePlayback">{{ enabled ? '暂停轮播' : '播放轮播' }}</button>
    </div>
  </el-config-provider>
</template>
