<script setup>
import { computed, nextTick, onMounted, onScopeDispose, reactive, ref, watch } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import AppButton from '@/shared/ui/AppButton.vue';
import { clearSession, session } from '@/shared/legacy/session.js';
import { createLegacyClient } from '@/shared/legacy/client.js';
import { isRecord } from '@/shared/http/client.js';
import { saveAssistantDraft } from '../assistant/handoff-draft.js';
import { clampPetPosition, createPointerDrag } from './pet-position.js';
import { usePetChat } from './use-pet-chat.js';

const router = useRouter();
const api = createLegacyClient({ token: () => session.token, expire: clearSession });
const { state, submit, stop } = usePetChat();
const open = ref(false),
  feedback = ref(''),
  prefsError = ref(''),
  saving = ref(false),
  prefsReady = ref(false);
const launcher = ref(/** @type {HTMLButtonElement|null} */ (null));
const panel = ref(/** @type {HTMLElement|null} */ (null));
const questionInput = ref(/** @type {HTMLTextAreaElement|null} */ (null));
const viewport = reactive({ width: window.innerWidth, height: window.innerHeight });
const petPosition = reactive({ x: viewport.width - 132, y: viewport.height - 270 });
const panelPosition = reactive({ x: viewport.width - 420, y: 110 });
const prefs = reactive({
  skin: 'daqiao',
  scale: 1,
  hidden: false,
  life: false,
  custom_url: '',
  custom_w: 0,
  custom_h: 0,
});
const skins = [
  {
    id: 'daqiao',
    name: '大乔',
    atlas: '/assets/ai-pet/xiaozhuan-atlas.webp',
    rows: 9,
    cols: 8,
    ratio: 147 / 120,
    idle: 0,
    count: 6,
  },
  {
    id: 'zhuan',
    name: '小转',
    atlas: '/assets/ai-pet/xiaozhuan-pet.png',
    rows: 1,
    cols: 1,
    ratio: 464 / 480,
    idle: 0,
    count: 1,
  },
  {
    id: 'xiaomao',
    name: '小毛',
    atlas: '/assets/ai-pet/xiaomao-atlas.webp',
    rows: 11,
    cols: 8,
    ratio: 1,
    idle: 4,
    count: 5,
  },
];
const skin = computed(() => skins.find((item) => item.id === prefs.skin) || skins[0]);
const customUrl = computed(() =>
  /^\/media\/pet_[0-9a-f]{32}$/.test(prefs.custom_url) ? prefs.custom_url : '',
);
const petSize = computed(() => ({ width: 100 * prefs.scale, height: 130 * prefs.scale + 26 }));
const panelSize = computed(() => ({
  width: Math.min(380, viewport.width - 24),
  height: Math.min(560, viewport.height - (viewport.width <= 760 ? 120 : 24)),
}));
const frame = ref(0),
  reduced = ref(false);
const spriteStyle = computed(() => ({
  width: '100px',
  height: `${100 * skin.value.ratio}px`,
  backgroundImage: `url("${skin.value.atlas}")`,
  backgroundSize: `${skin.value.cols * 100}px ${skin.value.rows * 100 * skin.value.ratio}px`,
  backgroundPosition: `${-(frame.value % skin.value.count) * 100}px ${-skin.value.idle * 100 * skin.value.ratio}px`,
}));
let prefsController = new AbortController(),
  disposed = false;
const drag = createPointerDrag();
let dragging = /** @type {'pet'|'panel'|null} */ (null),
  suppressClick = false;
let pointerId = -1;
let returnFocus = /** @type {HTMLElement|null} */ (null);
let feedbackTimer = /** @type {ReturnType<typeof setTimeout>|undefined} */ (undefined);

/** 从旧接口白名单读取偏好，避免把额外账号数据或聊天内容写入偏好。 @param {Record<string,unknown>} source 接口对象。 */
function applyPrefs(source) {
  prefs.skin = ['daqiao', 'zhuan', 'xiaomao', 'custom'].includes(String(source.skin))
    ? String(source.skin)
    : 'daqiao';
  prefs.scale = Math.max(0.6, Math.min(1.6, typeof source.scale === 'number' ? source.scale : 1));
  prefs.hidden = source.hidden === true;
  prefs.life = source.life === true;
  prefs.custom_url = typeof source.custom_url === 'string' ? source.custom_url : '';
  prefs.custom_w = typeof source.custom_w === 'number' ? source.custom_w : 0;
  prefs.custom_h = typeof source.custom_h === 'number' ? source.custom_h : 0;
}
/** 换账号先清理旧偏好并终止请求；同步失败保留当前可操作的宠物入口。 */
async function loadPrefs() {
  prefsController.abort();
  prefsController = new AbortController();
  const controller = prefsController;
  applyPrefs({});
  prefsError.value = '';
  saving.value = false;
  prefsReady.value = !session.token;
  closePanel(false);
  if (!session.token) return;
  try {
    const result = await api('/pet/prefs', { signal: controller.signal });
    if (!disposed && !controller.signal.aborted && isRecord(result) && result.synced === true) {
      applyPrefs(result);
      clampAll();
    }
    if (!disposed && !controller.signal.aborted && isRecord(result)) prefsReady.value = true;
  } catch {
    if (!disposed && !controller.signal.aborted)
      prefsError.value = '宠物偏好暂未同步，可稍后重新打开页面。';
  }
}
watch(() => [session.token, session.epoch, session.me?.id], loadPrefs, {
  immediate: true,
  flush: 'sync',
});

/** 原偏好接口是唯一账号偏好writer，保留life和自定义形象字段；不自动重试写入。 */
async function savePrefs() {
  clampAll();
  if (!session.token || saving.value || !prefsReady.value) return;
  const controller = prefsController;
  saving.value = true;
  prefsError.value = '';
  try {
    await api('/pet/prefs/save', { body: { ...prefs }, signal: controller.signal });
  } catch {
    if (!controller.signal.aborted && !disposed)
      prefsError.value = '偏好保存未确认，请稍后重新读取核对。';
  } finally {
    if (!controller.signal.aborted && !disposed) saving.value = false;
  }
}
/** 夹紧两个浮层，为移动导航和设备安全区域留白。 */
function clampAll() {
  Object.assign(petPosition, clampPetPosition(petPosition, viewport, petSize.value));
  Object.assign(panelPosition, clampPetPosition(panelPosition, viewport, panelSize.value));
}
/** 监听布局及软键盘视口变化，面板标题始终可以到达。 */
function resize() {
  viewport.width = window.visualViewport?.width || window.innerWidth;
  viewport.height = window.visualViewport?.height || window.innerHeight;
  clampAll();
}
/** 隐私模式仅降级为内存坐标，本地只保存几何位置。 */
function savePosition() {
  try {
    localStorage.setItem(
      'hc-vue-pet-position',
      JSON.stringify({ pet: { ...petPosition }, panel: { ...panelPosition } }),
    );
  } catch {
    /* 坐标保存失败不影响聊天。 */
  }
}
/** 仅恢复有限数字，损坏偏好不会影响界面启动。 */
function restorePosition() {
  try {
    const saved = JSON.parse(localStorage.getItem('hc-vue-pet-position') || '{}');
    for (const [key, point] of [
      ['pet', petPosition],
      ['panel', panelPosition],
    ]) {
      const candidate = saved[String(key)];
      if (isRecord(candidate) && Number.isFinite(candidate.x) && Number.isFinite(candidate.y))
        Object.assign(point, { x: candidate.x, y: candidate.y });
    }
  } catch {
    /* 使用默认位置。 */
  }
  clampAll();
}
/** 抚摸反馈短暂展示，重复触发时重置计时并尊重销毁清理。 */
function petting() {
  window.clearTimeout(feedbackTimer);
  feedback.value = '摸摸收到啦，今天也在这里陪你。';
  feedbackTimer = setTimeout(() => {
    feedback.value = '';
  }, 4000);
}
/** 打开对话后聚焦输入，关闭时归还到原操作按钮。 */
async function togglePanel() {
  if (suppressClick) {
    suppressClick = false;
    return;
  }
  petting();
  if (open.value) {
    closePanel();
    return;
  }
  returnFocus =
    document.activeElement instanceof window.HTMLElement ? document.activeElement : launcher.value;
  open.value = true;
  clampAll();
  await nextTick();
  questionInput.value?.focus();
}
/** 非模态窗关闭只隐藏界面；用户可通过停止按钮显式取消生成。 @param {boolean} [restore] 是否恢复开启者焦点。 */
function closePanel(restore = true) {
  open.value = false;
  if (restore)
    void nextTick(() => {
      if (returnFocus?.isConnected) returnFocus.focus();
      else launcher.value?.focus();
    });
}
/** Escape优先关闭宠物浮窗且不处理其余快捷键。 @param {KeyboardEvent} event 键盘事件。 */
function keydown(event) {
  if (event.key === 'Escape' && open.value && !event.defaultPrevented) {
    event.preventDefault();
    closePanel();
  }
}
/** 从可拖动表面开始手势；按钮和链接仍保持各自键盘行为。 @param {PointerEvent} event 指针事件。 @param {'pet'|'panel'} target 拖动目标。 */
function startDrag(event, target) {
  if (
    dragging ||
    event.button !== 0 ||
    (target === 'panel' &&
      event.target instanceof window.Element &&
      event.target.closest('button,a,input,select'))
  )
    return;
  dragging = target;
  pointerId = event.pointerId;
  suppressClick = false;
  drag.start(
    event.pointerId,
    event.clientX,
    event.clientY,
    target === 'pet' ? petPosition : panelPosition,
  );
}
/** 窗口级跟踪避免指针离开宠物后丢失拖动，其他指针不得接管。 @param {PointerEvent} event 指针事件。 */
function moveDrag(event) {
  if (!dragging) return;
  const point = drag.move(event.pointerId, event.clientX, event.clientY);
  if (!point) return;
  Object.assign(
    dragging === 'pet' ? petPosition : panelPosition,
    clampPetPosition(point, viewport, dragging === 'pet' ? petSize.value : panelSize.value),
  );
}
/** 释放或取消手势后保存坐标并屏蔽拖动产生的下一次click。 @param {PointerEvent} event 指针事件。 */
function endDrag(event) {
  if (!dragging || pointerId !== event.pointerId) return;
  const moved = drag.end(event.pointerId);
  if (dragging === 'pet') suppressClick = moved;
  dragging = null;
  pointerId = -1;
  savePosition();
}
/** 手动隐藏后保留恢复按钮，防止偏好开启后找不到宠物。 */
function hidePet() {
  prefs.hidden = true;
  closePanel();
  void savePrefs();
}
/** 只前往现有人工表单，由用户核对后提交，不执行模型动作。 */
async function handoff() {
  const latest = [...state.messages].reverse().find((message) => message.role === 'user');
  saveAssistantDraft(state.question || latest?.content || '');
  closePanel(false);
  await router.push('/support/new');
}
/** 过滤未知响应数组，模板只渲染普通文本。 @param {Record<string,unknown>|undefined} result 完成DTO。 @param {string} key 列表字段。 */
function records(result, key) {
  const items = result?.[key];
  return Array.isArray(items) ? items.filter(isRecord).slice(0, 8) : [];
}
/** 建议仅填入问题草稿，仍需用户点击发送。 @param {unknown} result 建议列表。 */
function suggestions(result) {
  return Array.isArray(result) ? result.filter((item) => typeof item === 'string').slice(0, 6) : [];
}
/** 业务卡片只允许正整数编号形成本站路由。 @param {unknown} value 原编号。 */
function itemId(value) {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? String(id) : '';
}
/** 监听系统减少动态效果设置。 @param {MediaQueryListEvent|MediaQueryList} event 媒体查询事件。 */
function motionChange(event) {
  reduced.value = event.matches;
}
const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
onMounted(() => {
  restorePosition();
  resize();
  motion && motionChange(motion);
  motion?.addEventListener('change', motionChange);
  window.addEventListener('resize', resize);
  window.visualViewport?.addEventListener('resize', resize);
  window.addEventListener('pointermove', moveDrag);
  window.addEventListener('pointerup', endDrag);
  window.addEventListener('pointercancel', endDrag);
  document.addEventListener('keydown', keydown);
});
const frameTimer = setInterval(() => {
  if (prefs.life && !reduced.value && !prefs.hidden && !document.hidden) frame.value++;
}, 220);
onScopeDispose(() => {
  disposed = true;
  prefsController.abort();
  clearInterval(frameTimer);
  window.clearTimeout(feedbackTimer);
  motion?.removeEventListener('change', motionChange);
  window.removeEventListener('resize', resize);
  window.visualViewport?.removeEventListener('resize', resize);
  window.removeEventListener('pointermove', moveDrag);
  window.removeEventListener('pointerup', endDrag);
  window.removeEventListener('pointercancel', endDrag);
  document.removeEventListener('keydown', keydown);
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="!prefs.hidden"
      class="zj-pet"
      :style="{ left: petPosition.x + 'px', top: petPosition.y + 'px' }"
    >
      <button
        ref="launcher"
        type="button"
        class="zj-pet-launcher"
        data-pet-launcher
        :aria-expanded="open"
        aria-controls="zj-pet-dialog"
        aria-label="摸摸小转，打开或关闭对话；可拖动移动"
        :style="{ width: petSize.width + 'px', height: petSize.height + 'px' }"
        @pointerdown="startDrag($event, 'pet')"
        @click="togglePanel"
      >
        <span class="zj-pet-image" :style="{ transform: `scale(${prefs.scale})` }"
          ><img
            v-if="prefs.skin === 'custom' && customUrl"
            :src="customUrl"
            alt="你的自定义宠物"
            draggable="false" /><span
            v-else
            class="zj-pet-sprite"
            :style="spriteStyle"
            aria-hidden="true"
        /></span>
        <span class="zj-pet-name"
          >{{ prefs.skin === 'custom' ? '我的桌宠' : skin.name }} · 聊聊</span
        >
      </button>
      <span v-if="feedback" class="zj-pet-feedback" role="status">{{ feedback }}</span>
    </div>
    <button
      v-else
      type="button"
      class="zj-pet-restore"
      @click="
        prefs.hidden = false;
        savePrefs();
      "
    >
      显示小转
    </button>
    <section
      v-if="open && !prefs.hidden"
      id="zj-pet-dialog"
      ref="panel"
      class="zj-pet-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="zj-pet-title"
      :style="{
        left: panelPosition.x + 'px',
        top: panelPosition.y + 'px',
        width: panelSize.width + 'px',
        height: panelSize.height + 'px',
      }"
    >
      <header class="zj-pet-title" @pointerdown="startDrag($event, 'panel')">
        <div>
          <b id="zj-pet-title">转角 AI · {{ prefs.skin === 'custom' ? '我的桌宠' : skin.name }}</b
          ><small>拖动标题移动对话窗</small>
        </div>
        <button type="button" aria-label="关闭小转对话" @click="closePanel()">×</button>
      </header>
      <div class="zj-pet-settings">
        <label
          >角色<select
            v-model="prefs.skin"
            aria-label="宠物角色"
            :disabled="saving || !prefsReady"
            @change="
              frame = 0;
              savePrefs();
            "
          >
            <option v-for="entry in skins" :key="entry.id" :value="entry.id">
              {{ entry.name }}
            </option>
            <option v-if="customUrl" value="custom">我的桌宠</option>
          </select></label
        ><label
          >大小<input
            v-model.number="prefs.scale"
            aria-label="宠物大小"
            type="range"
            min="0.6"
            max="1.6"
            step="0.1"
            :disabled="saving || !prefsReady"
            @change="savePrefs" /></label
        ><button type="button" :disabled="saving || !prefsReady" @click="hidePet">隐藏</button>
      </div>
      <p v-if="prefsError" class="zj-pet-error" role="status">
        {{ prefsError }} <button type="button" @click="loadPrefs">重新读取偏好</button>
      </p>
      <div
        class="zj-pet-messages"
        aria-label="小转聊天记录"
        aria-live="polite"
        aria-relevant="additions text"
      >
        <p v-if="!state.messages.length && !state.partial" class="zj-pet-welcome">
          闲置、订单、校园生活，都可以聊。请勿发送密码、恢复码等凭据。
        </p>
        <article
          v-for="(message, index) in state.messages"
          :key="index"
          :class="['zj-pet-message', message.role]"
        >
          <b>{{ message.role === 'user' ? '你' : '小转' }}</b>
          <p>{{ message.content }}</p>
          <template v-if="message.result"
            ><small v-if="message.result.mode">模式：{{ message.result.mode }}</small>
            <ul v-if="records(message.result, 'sources').length">
              <li v-for="(source, n) in records(message.result, 'sources')" :key="n">
                {{ source.title || source.source }}
              </li>
            </ul>
            <div v-for="(product, n) in records(message.result, 'products')" :key="'p' + n">
              <RouterLink v-if="itemId(product.id)" :to="'/products/' + itemId(product.id)">{{
                product.title || '查看商品'
              }}</RouterLink>
            </div>
            <div v-for="(order, n) in records(message.result, 'orders')" :key="'o' + n">
              <RouterLink v-if="itemId(order.id)" to="/orders"
                >{{ order.title || '查看订单' }} · {{ order.status_label }}</RouterLink
              >
            </div>
            <div v-if="records(message.result, 'links').length">
              <a href="/legacy-ai.html#home">在完整 AI 中查看相关业务入口</a>
            </div>
            <button
              v-for="(suggestion, n) in suggestions(message.result.suggestions)"
              :key="'s' + n"
              type="button"
              class="zj-pet-suggestion"
              @click="
                state.question = suggestion;
                questionInput?.focus();
              "
            >
              {{ suggestion }}
            </button>
            <p
              v-if="
                message.result.action === 'transfer' || message.result.action === 'leave_message'
              "
            >
              可填写人工工单，核对后由你提交。
            </p></template
          >
        </article>
        <article v-if="state.partial" class="zj-pet-message assistant">
          <b>小转 · {{ state.busy ? '正在生成' : '回答未完成' }}</b>
          <p>{{ state.partial }}</p>
        </article>
        <p v-else-if="state.busy" role="status">小转正在思考…</p>
      </div>
      <p v-if="state.error" class="zj-pet-error" role="alert">{{ state.error }}</p>
      <form v-if="session.token" class="zj-pet-form" @submit.prevent="submit">
        <label for="zj-pet-question">想和小转说什么？</label
        ><textarea
          id="zj-pet-question"
          ref="questionInput"
          v-model="state.question"
          rows="2"
          maxlength="300"
          placeholder="输入问题，最多300字"
        />
        <div>
          <AppButton type="submit" :disabled="state.busy">{{
            state.error && state.turn ? '重试本次问题' : '发送'
          }}</AppButton
          ><AppButton v-if="state.busy" variant="quiet" @click="stop">停止生成</AppButton
          ><AppButton variant="quiet" @click="handoff">转人工</AppButton>
        </div>
      </form>
      <p v-else class="zj-pet-login"><RouterLink to="/login">登录后开始聊天</RouterLink></p>
      <footer>
        <button type="button" @click="petting">摸摸</button
        ><a href="/legacy-ai.html#home">完整 AI / 高级设置</a>
      </footer>
    </section>
  </Teleport>
</template>

<style scoped>
.zj-pet,
.zj-pet-panel,
.zj-pet-restore {
  position: fixed;
  z-index: 35;
  font-family: var(--font-body);
  color: var(--color-text);
}
.zj-pet-launcher {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-direction: column;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.zj-pet-launcher:active,
.zj-pet-title:active {
  cursor: grabbing;
}
.zj-pet-image {
  display: block;
  transform-origin: center bottom;
  pointer-events: none;
}
.zj-pet-image img {
  width: 100px;
  height: 123px;
  object-fit: contain;
}
.zj-pet-sprite {
  display: block;
  background-repeat: no-repeat;
}
.zj-pet-name {
  font-size: 12px;
  white-space: nowrap;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  padding: 3px 10px;
  border-radius: 16px;
  box-shadow: var(--shadow-card);
  position: relative;
}
.zj-pet-feedback {
  position: absolute;
  bottom: 100%;
  right: 0;
  width: 170px;
  padding: 9px 12px;
  background: var(--color-topic-study-bg);
  color: var(--color-topic-study-ink);
  border-radius: 12px;
  font-size: 12px;
  pointer-events: none;
}
.zj-pet-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-dialog);
  box-shadow: var(--shadow-overlay);
}
.zj-pet-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--color-topic-study-bg);
  padding: 12px 16px;
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.zj-pet-title small {
  display: block;
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 3px;
}
.zj-pet-title button {
  font-size: 25px;
  min-width: 40px;
  min-height: 40px;
}
.zj-pet-panel button,
.zj-pet-restore {
  cursor: pointer;
}
.zj-pet-panel button:not(.app-button) {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-link);
  padding: 5px 9px;
  min-height: 32px;
}
.zj-pet-settings {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
}
.zj-pet-settings label {
  display: flex;
  align-items: center;
  gap: 4px;
}
.zj-pet-settings select {
  max-width: 90px;
  min-height: 32px;
}
.zj-pet-settings input {
  width: 66px;
  accent-color: var(--color-link);
}
.zj-pet-messages {
  flex: 1;
  min-height: 45px;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 12px;
}
.zj-pet-welcome {
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.7;
}
.zj-pet-message {
  padding: 10px 12px;
  margin-bottom: 10px;
  border-radius: 12px;
  background: var(--color-surface-subtle);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.zj-pet-message.user {
  margin-left: 28px;
  background: var(--color-topic-study-bg);
}
.zj-pet-message.assistant {
  margin-right: 12px;
}
.zj-pet-message p {
  white-space: pre-wrap;
  line-height: 1.65;
  margin: 5px 0;
}
.zj-pet-message small {
  color: var(--color-text-muted);
}
.zj-pet-message ul {
  padding-left: 18px;
}
.zj-pet-message a,
.zj-pet-panel footer a,
.zj-pet-login a {
  color: var(--color-link);
}
.zj-pet-suggestion {
  margin: 5px 4px 0 0;
  font-size: 12px;
  text-align: left;
}
.zj-pet-error {
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-danger);
  padding: 0 12px;
  margin: 6px 0;
}
.zj-pet-form {
  padding: 10px 12px;
  border-top: 1px solid var(--color-border);
}
.zj-pet-form label {
  display: block;
  font-size: 12px;
  margin-bottom: 6px;
}
.zj-pet-form textarea {
  box-sizing: border-box;
  width: 100%;
  max-height: 100px;
  resize: vertical;
  border: 1px solid var(--color-control-border);
  border-radius: 8px;
  padding: 8px;
  font: inherit;
  font-size: 13px;
}
.zj-pet-form > div {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.zj-pet-form .app-button {
  min-width: 64px;
  min-height: 36px;
  padding: 6px 10px;
  font-size: 12px;
}
.zj-pet-panel footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px 10px;
  font-size: 12px;
  gap: 8px;
}
.zj-pet-login {
  padding: 8px 12px;
}
.zj-pet-restore {
  right: 12px;
  bottom: 110px;
  background: var(--color-topic-study-bg);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 10px 14px;
}
.zj-pet-launcher:focus-visible,
.zj-pet-panel :focus-visible,
.zj-pet-restore:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .zj-pet *,
  .zj-pet-panel * {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
</style>
