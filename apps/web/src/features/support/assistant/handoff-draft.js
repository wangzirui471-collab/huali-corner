import { watch } from 'vue';
import { session } from '@/shared/legacy/session.js';

/** @type {{epoch: number, accountId: unknown, question: string}|null} 只保存用户原问题，不保存模型回答或认证令牌。 */
let draft = null;
// 草稿允许跨一次页面导航，身份一变立即清除；不使用 URL、localStorage 或 sessionStorage。
watch(
  () => [session.epoch, session.token, session.me?.id],
  () => {
    draft = null;
  },
  { flush: 'sync' },
);

/** 保存当前账号可检查的原问题，仅供人工工单表单预填。 @param {string} question 用户原问题。 */
export function saveAssistantDraft(question) {
  if (!session.token || !question.trim()) return;
  draft = { epoch: session.epoch, accountId: session.me?.id, question };
}

/** 同账号人工表单只消费一次；不提交工单、不打开会话。 @returns {string} 预填正文或空串。 */
export function consumeAssistantDraft() {
  const current = draft;
  draft = null;
  return current &&
    session.token &&
    current.epoch === session.epoch &&
    current.accountId === session.me?.id
    ? current.question
    : '';
}
