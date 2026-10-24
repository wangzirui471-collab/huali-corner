<script setup>
import { onScopeDispose, ref, watch } from 'vue';
import { session } from '../legacy/session.js';
const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  ticket: { type: Number, default: 0 },
});
const url = ref(''),
  failed = ref(false);
let blob = '',
  controller = new AbortController(),
  generation = 0;
/** 只允许同源媒体或已有同源静态素材；不向第三方发送认证头。 */
function reset() {
  controller.abort();
  controller = new AbortController();
  generation++;
  if (blob) URL.revokeObjectURL(blob);
  blob = '';
  failed.value = false;
  url.value = /^\/(?:media\/[\w-]+|assets\/[\w/.-]+|brand\/[\w.-]+)$/.test(props.src)
    ? props.src
    : '';
}
/** img 无法携带 Bearer；失败后只对精确媒体路径尝试认证 Blob。 */
async function authenticate() {
  if (!session.token || !/^\/media\/[\w-]+$/.test(props.src) || blob) {
    failed.value = true;
    return;
  }
  const current = generation,
    token = session.token;
  try {
    const response = await fetch(props.src + (props.ticket ? `?ticket_id=${props.ticket}` : ''), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
      redirect: 'error',
      credentials: 'same-origin',
    });
    if (!response.ok || !/^image\//.test(response.headers.get('content-type') || ''))
      throw new Error('图片读取失败');
    const content = await response.blob();
    if (current !== generation || token !== session.token) return;
    blob = URL.createObjectURL(content);
    url.value = blob;
  } catch {
    if (current === generation) failed.value = true;
  }
}
watch(() => [props.src, props.ticket, session.token], reset, { immediate: true });
onScopeDispose(() => {
  reset();
  url.value = '';
});
</script>
<template>
  <img v-if="url && !failed" :src="url" :alt="alt" loading="lazy" @error="authenticate" /><span
    v-else
    class="image-fallback"
    role="img"
    :aria-label="alt || '图片不可用'"
    >{{ failed ? '图片暂不可见' : '暂无图片' }}</span
  >
</template>
<style scoped>
img,
.image-fallback {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: var(--color-canvas);
  border-radius: inherit;
}
.image-fallback {
  min-height: 80px;
  display: grid;
  place-items: center;
  color: var(--color-text-muted);
  font-size: 13px;
}
</style>
