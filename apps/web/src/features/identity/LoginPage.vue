<script setup>
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElInput } from 'element-plus';
import 'element-plus/theme-chalk/el-input.css';
import AppButton from '@/shared/ui/AppButton.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
import { session } from '@/shared/legacy/session.js';
import { children, text } from '@/shared/legacy/dto.js';
import { useLegacyApi, useAction } from '@/shared/legacy/use-task.js';
import { login, register, resetPassword } from './auth.js';
const api = useLegacyApi();
const router = useRouter(),
  route = useRoute(),
  action = useAction();
const mode = ref('login'),
  recovery = ref(''),
  agree = ref(false);
const form = reactive({
  phone: '',
  password: '',
  confirm: '',
  nickname: '',
  college: '',
  grade: '',
  major: '',
  recovery_code: '',
});
const colleges = computed(() =>
  children(session.config, 'colleges').map(
    (item) => text(item, 'source_name') || text(item, 'name'),
  ),
);
const grades = computed(() =>
  Array.isArray(session.config.grades) ? session.config.grades.map(String) : [],
);
/** 只在服务端成功后跳转；注册/找回必须先保存一次性恢复码。 */
async function submit() {
  await action.run(
    async () => {
      if (mode.value !== 'login' && (form.password.length < 6 || form.password !== form.confirm))
        throw new Error('新密码至少 6 位，且两次输入必须一致');
      if (mode.value === 'register') {
        if (!agree.value) throw new Error('请先确认模拟交易与隐私说明');
        recovery.value = await register(form, api);
        continueAfterLogin();
      } else if (mode.value === 'recover')
        recovery.value = await resetPassword(
          {
            phone: form.phone,
            new_password: form.password,
            recovery_code: form.recovery_code,
          },
          false,
          api,
        );
      else {
        await login(form.phone, form.password, api);
        continueAfterLogin();
      }
      form.password = '';
      form.confirm = '';
      form.recovery_code = '';
    },
    mode.value === 'recover' ? '密码已重置，请保存新恢复码并重新登录' : '账号已准备好',
  );
}
/** 仅接受本站路径作为登录回跳地址，避免开放重定向。 */
function continueAfterLogin() {
  const next =
    typeof route.query.next === 'string' && /^\/(?!\/)/.test(route.query.next)
      ? route.query.next
      : '/';
  void router.replace(next);
}
</script>
<template>
  <section class="auth-layout">
    <div class="auth-story">
      <span class="eyebrow">HUALI CORNER</span>
      <h1>下一段故事，<br />从转角开始。</h1>
      <p>让闲置有去处，让同学有照应。</p>
      <p class="muted">手机号或邮箱尚未验证；当前订单与付款均为模拟。</p>
    </div>
    <div class="panel auth-panel">
      <template v-if="recovery"
        ><h2>请私下保存账号恢复码</h2>
        <p>恢复码仅在本次显示。修改或找回密码后，旧恢复码和已登录会话失效。</p>
        <code class="recovery-code">{{ recovery }}</code
        ><AppButton
          @click="
            recovery = '';
            mode = 'login';
            session.me && continueAfterLogin();
          "
          >已保存，继续</AppButton
        ></template
      ><template v-else
        ><h2>
          {{ mode === 'register' ? '加入华立转角' : mode === 'recover' ? '找回账号' : '欢迎回来' }}
        </h2>
        <div class="tabs">
          <button
            v-for="item in [
              { key: 'login', label: '登录' },
              { key: 'register', label: '注册' },
              { key: 'recover', label: '恢复码找回' },
            ]"
            :key="item.key"
            :aria-pressed="mode === item.key"
            @click="
              mode = item.key;
              action.error.value = '';
            "
          >
            {{ item.label }}
          </button>
        </div>
        <TaskFeedback :error="action.error.value" :notice="action.notice.value" />
        <form class="form-stack" @submit.prevent="submit">
          <label
            >手机号或邮箱<ElInput
              v-model="form.phone"
              required
              maxlength="120"
              autocomplete="username" /></label
          ><template v-if="mode === 'register'"
            ><label>昵称<ElInput v-model="form.nickname" required maxlength="24" /></label
            ><label
              >学院<select v-model="form.college" required>
                <option value="">请选择学院</option>
                <option v-for="college in colleges" :key="college">{{ college }}</option>
              </select></label
            ><label
              >入学年份<select v-model="form.grade" required>
                <option value="">请选择年级</option>
                <option v-for="grade in grades" :key="grade">{{ grade }}</option>
              </select></label
            ><label>专业（可选）<ElInput v-model="form.major" maxlength="80" /></label></template
          ><label v-if="mode === 'recover'"
            >账号恢复码<ElInput
              v-model="form.recovery_code"
              type="password"
              required
              autocomplete="off" /></label
          ><label
            >{{ mode === 'login' ? '密码' : '新密码'
            }}<ElInput
              v-model="form.password"
              type="password"
              show-password
              required
              maxlength="128"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" /></label
          ><label v-if="mode !== 'login'"
            >再次输入新密码<ElInput
              v-model="form.confirm"
              type="password"
              required
              autocomplete="new-password" /></label
          ><label v-if="mode === 'register'" class="checkbox-line"
            ><input
              v-model="agree"
              type="checkbox"
              required
            />我了解模拟交易及必要账号、内容、订单记录的保存，不提交身份证、宿舍门牌或支付信息。</label
          ><AppButton type="submit" :loading="action.busy.value">{{
            mode === 'login' ? '登录' : mode === 'register' ? '注册并登录' : '重置密码'
          }}</AppButton>
        </form></template
      >
    </div>
  </section>
</template>
