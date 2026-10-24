<script setup>
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { session, clearSession, roleRank } from '@/shared/legacy/session.js';
import { row, text, number, children } from '@/shared/legacy/dto.js';
import { useLoad, useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import { createProfileEditor } from './profile.js';
import { resetPassword } from './auth.js';
import AppButton from '@/shared/ui/AppButton.vue';
import AppDialog from '@/shared/ui/AppDialog.vue';
import LoadBoundary from '@/shared/ui/LoadBoundary.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import AuthenticatedImage from '@/shared/ui/AuthenticatedImage.vue';
import ProductCard from '@/features/catalog/ProductCard.vue';
const route = useRoute(),
  router = useRouter(),
  action = useAction();
const own = !route.params.id || Number(route.params.id) === number(session.me, 'id');
const editor = ref(/** @type {ReturnType<typeof createProfileEditor>|null} */ (null));
const comparison = ref(/** @type {import('@/shared/legacy/dto.js').Row|null} */ (null));
const file = ref(/** @type {File|null} */ (null)),
  uploadId = ref(''),
  preview = ref('');
const security = ref(false),
  oldPassword = ref(''),
  newPassword = ref(''),
  confirmation = ref(''),
  recovery = ref('');
const profile = useLoad(async (signal) => {
  const result = row(
    await api(own ? '/user/profile' : '/profile?id=' + route.params.id, { signal }),
  );
  if (own && !editor.value) editor.value = createProfileEditor(result);
  return result;
});
const friendship = useLoad(async (signal) =>
  !own && session.me ? row(await api('/friend/state?id=' + route.params.id, { signal })) : null,
);
const user = computed(() =>
  own ? profile.data.value : profile.data.value?.user ? row(profile.data.value.user) : null,
);
const tiles = [
  { to: '/orders', label: '我的订单' },
  { to: '/my-products', label: '我发布的' },
  { to: '/favorites', label: '我的收藏' },
  { to: '/cart', label: '取货清单' },
  { to: '/friends', label: '好友与申请' },
  { to: '/messages', label: '消息与通知' },
  { to: '/support', label: '帮助与售后' },
];
/** 明确成功后更新身份与版本；失败不清除编辑输入。 */
async function save() {
  await action.run(async () => {
    if (!editor.value) return;
    const result = row(await api('/user/profile', { body: editor.value.payload() }));
    editor.value.compare(result);
    editor.value.adopt(false);
    session.me = result;
    await profile.reload();
  }, '资料已保存');
}
/** 冲突时只显示服务器对照，采用哪个版本由用户选择。 */
async function compare() {
  await action.run(async () => {
    const result = row(await api('/user/profile'));
    editor.value?.compare(result);
    comparison.value = result;
  }, '已读取服务器版本，你的输入仍保留');
}
/** 选择保留输入或用服务器内容替换，不能无提示重试覆盖。 @param {boolean} replace 是否替换。 */
function adopt(replace) {
  editor.value?.adopt(replace);
  comparison.value = null;
}
/** 选择头像只修改本次待上传文件，不直接公开。 @param {Event} event 文件事件。 */
function selectFile(event) {
  file.value = /** @type {HTMLInputElement} */ (event.target).files?.[0] || null;
  uploadId.value = '';
  preview.value = '';
}
/** 私密上传先预览，确认后才改变公开头像；原文件最大 2 MiB。 */
async function upload() {
  await action.run(async () => {
    const image = file.value;
    if (
      !image ||
      image.size > 2 * 1024 * 1024 ||
      !['image/jpeg', 'image/png', 'image/webp'].includes(image.type)
    )
      throw new Error('请选择不超过 2 MiB 的 JPEG、PNG 或 WebP 图片');
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('图片读取失败'));
      reader.readAsDataURL(image);
    });
    const result = row(await api('/user/avatar/upload', { body: { content } }));
    uploadId.value = text(result, 'upload_id');
    preview.value =
      text(result, 'url') || text(result, 'preview_url') || '/media/' + uploadId.value;
    if (!/^ua_[0-9a-f]{32}$/.test(uploadId.value)) throw new Error('头像上传响应缺少有效编号');
  }, '已上传待选头像，确认后才会公开');
}
/** 选择或移除头像同样携带资料版本，避免覆盖另一标签页的更新。 @param {boolean} [remove] 是否移除。 */
async function selectAvatar(remove = false) {
  if (remove && !window.confirm('确认移除当前公开头像？')) return;
  await action.run(async () => {
    if (!editor.value || (!remove && !uploadId.value)) throw new Error('请先上传头像');
    const result = row(
      await api('/user/avatar', {
        body: {
          upload_id: remove ? null : uploadId.value,
          profile_version: editor.value.payload().profile_version,
        },
      }),
    );
    editor.value.compare(result);
    editor.value.adopt(false);
    session.me = result;
    uploadId.value = '';
    preview.value = '';
    await profile.reload();
  }, '头像已更新');
}
/** 改密后旧会话失效，一次性恢复码留在当前对话框，主动确认后离开。 */
async function changePassword() {
  await action.run(async () => {
    if (newPassword.value !== confirmation.value || newPassword.value.length < 6)
      throw new Error('两次新密码需一致且至少 6 位');
    recovery.value = await resetPassword(
      {
        phone: text(session.me, 'phone'),
        old_password: oldPassword.value,
        new_password: newPassword.value,
      },
      true,
      api,
    );
    oldPassword.value = '';
    newPassword.value = '';
    confirmation.value = '';
  }, '密码已更新，请保存恢复码');
}
/** 退出先撤销当前服务器会话；网络失败仍允许用户显式只清本机。 @param {boolean} [local] 只退出本机。 */
async function logout(local = false) {
  await action.run(async () => {
    if (!local) await api('/auth/logout', { body: {} });
    clearSession();
    await router.push('/login');
  }, '已退出');
}
/** 注销后释放关联交易由原业务服务处理，页面必须先说明后果。 */
async function deactivate() {
  if (!window.confirm('注销会终止登录并处置关联商品和未完成订单，历史记录保留。确认注销账号？'))
    return;
  await action.run(async () => {
    await api('/auth/deactivate', { body: {} });
    clearSession();
    await router.push('/');
  }, '账号已注销');
}
/** 公开主页的好友入口先申请，普通私聊仍由服务端核验好友关系。 */
async function contact() {
  await action.run(async () => {
    const result = row(await api('/rooms/private', { body: { peer: Number(route.params.id) } }));
    await router.push('/messages/' + number(result, 'id'));
  });
}
</script>
<template>
  <section>
    <header class="section-heading">
      <div>
        <span class="eyebrow">CAMPUS PROFILE</span>
        <h1>{{ own ? '我的转角' : '同学主页' }}</h1>
      </div>
      <RouterLink v-if="own && roleRank() >= 1" to="/workspace">进入工作台</RouterLink>
    </header>
    <TaskFeedback :error="action.error.value" :notice="action.notice.value" /><LoadBoundary
      :loading="profile.loading.value"
      :error="profile.error.value"
      :forbidden="profile.forbidden.value"
      @retry="profile.reload"
      ><template v-if="user"
        ><section class="panel profile-summary">
          <div class="profile-avatar">
            <AuthenticatedImage
              :src="text(user, 'avatar_url')"
              :alt="text(user, 'nickname') + '的头像'"
            />
          </div>
          <div>
            <h2>{{ text(user, 'nickname') }}</h2>
            <p>{{ text(user, 'college') }} · {{ text(user, 'major') }}</p>
            <p class="muted">{{ text(user, 'bio', '这个同学还没有填写简介。') }}</p>
            <span class="pill"
              >信誉 {{ number(user, 'score') }} ·
              {{ text(user, 'star_label', text(user, 'badge', '校园同学')) }}</span
            >
          </div>
        </section>
        <template v-if="own"
          ><nav class="account-tiles" aria-label="个人中心功能">
            <RouterLink v-for="tile in tiles" :key="tile.to" :to="tile.to"
              >{{ tile.label }} <span>↗</span></RouterLink
            >
          </nav>
          <div class="two-column">
            <section class="panel">
              <h2>个人资料</h2>
              <form v-if="editor" class="form-grid" @submit.prevent="save">
                <label
                  >昵称<input
                    v-model="editor.form.nickname"
                    required
                    maxlength="24"
                    autocomplete="nickname" /></label
                ><label>专业<input v-model="editor.form.major" maxlength="80" /></label
                ><label
                  >学历层次<select v-model="editor.form.degree_level">
                    <option value="unspecified">暂不填写</option>
                    <option value="bachelor">本科</option>
                    <option value="junior_college">专科</option>
                    <option value="other">其他</option>
                  </select></label
                ><label
                  >在读状态<select v-model="editor.form.study_status">
                    <option value="unspecified">暂不填写</option>
                    <option value="studying">在读</option>
                    <option value="graduated">已毕业</option>
                    <option value="other">其他</option>
                  </select></label
                ><label class="full-width"
                  >个人简介<textarea v-model="editor.form.bio" maxlength="300" rows="4" />
                </label>
                <p class="muted full-width">
                  学院：{{ text(user, 'college') }}。学院信息不能在此修改。
                </p>
                <div class="actions full-width">
                  <AppButton type="submit" :loading="action.busy.value">保存资料</AppButton
                  ><AppButton variant="secondary" :disabled="action.busy.value" @click="compare"
                    >核对服务器版本</AppButton
                  >
                </div>
              </form>
              <div v-if="comparison" class="notice-panel">
                <h3>服务器资料对照</h3>
                <p>
                  版本 {{ number(comparison, 'profile_version') }} ·
                  {{ text(comparison, 'nickname') }} · {{ text(comparison, 'major') }}
                </p>
                <p>{{ text(comparison, 'bio') }}</p>
                <div class="actions">
                  <AppButton variant="secondary" @click="adopt(false)"
                    >保留输入并采用此版本</AppButton
                  ><AppButton variant="quiet" @click="adopt(true)">用服务器资料替换输入</AppButton>
                </div>
              </div>
            </section>
            <section class="panel">
              <h2>我的头像</h2>
              <p class="muted">JPEG、PNG、WebP，原图不超过 2 MiB。上传后先确认再公开。</p>
              <label
                >选择头像<input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  @change="selectFile"
              /></label>
              <div v-if="preview" class="profile-avatar">
                <AuthenticatedImage :src="preview" alt="尚未公开的头像预览" />
              </div>
              <div class="actions">
                <AppButton variant="secondary" :loading="action.busy.value" @click="upload"
                  >上传并预览</AppButton
                ><AppButton v-if="uploadId" :loading="action.busy.value" @click="selectAvatar()"
                  >确认设为头像</AppButton
                ><AppButton
                  variant="quiet"
                  :disabled="action.busy.value"
                  @click="selectAvatar(true)"
                  >移除当前头像</AppButton
                >
              </div>
            </section>
          </div>
          <section class="panel">
            <h2>账号安全</h2>
            <div class="actions">
              <AppButton variant="secondary" @click="security = true">修改密码</AppButton
              ><AppButton variant="secondary" :loading="action.busy.value" @click="logout()"
                >退出登录</AppButton
              ><AppButton v-if="action.error.value" variant="quiet" @click="logout(true)"
                >仅清除本机登录</AppButton
              ><AppButton variant="quiet" @click="deactivate">注销账号</AppButton>
            </div>
          </section></template
        ><template v-else
          ><div class="actions">
            <RouterLink :to="{ path: '/friends', query: { target: route.params.id } }">{{
              text(friendship.data.value, 'state') === 'accepted'
                ? '已是好友 · 查看好友'
                : text(friendship.data.value, 'state') === 'pending_out'
                  ? '申请已发出'
                  : text(friendship.data.value, 'state') === 'pending_in'
                    ? '处理对方申请'
                    : '申请好友'
            }}</RouterLink
            ><AppButton variant="secondary" @click="contact">发送私信</AppButton
            ><RouterLink :to="{ path: '/support/new', query: { type: 'report' } }"
              >举报与申诉</RouterLink
            >
          </div>
          <h2>同学发布的闲置</h2>
          <div class="product-grid">
            <ProductCard
              v-for="product in children(profile.data.value, 'products')"
              :key="number(product, 'id')"
              :product="product"
            /></div></template></template></LoadBoundary
    ><AppDialog :open="security" title="修改密码" @close="security = false"
      ><TaskFeedback :error="action.error.value" :notice="action.notice.value" /><template
        v-if="recovery"
        ><p>请保存新恢复码，仅本次显示。旧会话已失效。</p>
        <code class="recovery-code">{{ recovery }}</code
        ><AppButton @click="router.push('/login')">我已保存，重新登录</AppButton></template
      >
      <form v-else class="stack-form" @submit.prevent="changePassword">
        <label
          >原密码<input
            v-model="oldPassword"
            type="password"
            required
            autocomplete="current-password" /></label
        ><label
          >新密码<input
            v-model="newPassword"
            type="password"
            required
            minlength="6"
            autocomplete="new-password" /></label
        ><label
          >确认新密码<input
            v-model="confirmation"
            type="password"
            required
            autocomplete="new-password" /></label
        ><AppButton type="submit" :loading="action.busy.value">确认修改并使旧会话失效</AppButton>
      </form></AppDialog
    >
  </section>
</template>
