<script setup>
/** 稳定的原页面容器；Vue 不接管内部字符串模板，也不在切页时卸载 AI。 */
import {onMounted, onBeforeUnmount, watch} from 'vue';
import {useRoute} from 'vue-router';
import {startApplication, schedulePrefetch} from './runtime.js';
import {render} from '../router.js?v=market-carousel-v2';
import {bumpRenderId, clearPoll, state} from '../core/state.js';
import {stopProgress} from '../core/progress.js';

const route = useRoute();
let dispose;
let prefetchTimer;

/** 挂载后恢复原账号和配置，只注册一套原站事件。 */
onMounted(() => { dispose = startApplication(); });

/** Vue Router 唯一驱动换页；同组件复用时保留宠物和原站会话。 */
watch(() => route.fullPath, () => {
  void render();
  clearTimeout(prefetchTimer);
  prefetchTimer = setTimeout(schedulePrefetch, 900);
});

/** 应用卸载时清除页面资源与全局监听，避免开发重载叠加事件。 */
onBeforeUnmount(() => {
  dispose?.();
  bumpRenderId();
  stopProgress();
  clearTimeout(prefetchTimer);
  clearPoll();
  state.homeView?.dispose();
  state.homeView = null;
  for (const url of state.mediaURLs) URL.revokeObjectURL(url);
  state.mediaURLs.clear();
});
</script>

<template><div id="app"><p class="loading">正在打开转角…</p></div></template>
