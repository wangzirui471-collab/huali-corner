import { reactive } from 'vue';
import { number, text } from '@/shared/legacy/dto.js';
/** 带归属与版本保护的资料编辑模型，读取冲突对照不修改尚未保存的输入。 @param {import('@/shared/legacy/dto.js').Row} initial 原始资料。 */
export function createProfileEditor(initial) {
  const owner = number(initial, 'id');
  const fields = ['nickname', 'major', 'bio', 'degree_level', 'study_status'];
  const form = reactive(
    /** @type {Record<string,string>} */ (
      Object.fromEntries(fields.map((key) => [key, text(initial, key)]))
    ),
  );
  let version = number(initial, 'profile_version');
  let latest = /** @type {import('@/shared/legacy/dto.js').Row|null} */ (null);
  /** 生成原版本请求，不暗中覆盖并发修改。 */
  function payload() {
    return { ...form, profile_version: version };
  }
  /** 仅保存同一账号的版本对照，拒绝格式不完整的返回值。 @param {import('@/shared/legacy/dto.js').Row} value 服务端资料。 */
  function compare(value) {
    if (
      number(value, 'id') !== owner ||
      !Number.isSafeInteger(value.profile_version) ||
      Number(value.profile_version) < 0
    )
      throw new Error('资料归属或版本不合法');
    latest = value;
  }
  /** 用户明确选择保留输入或替换后，才采用对照版本。 @param {boolean} replace 是否替换输入。 */
  function adopt(replace) {
    if (!latest) return;
    version = number(latest, 'profile_version');
    if (replace) for (const key of fields) form[key] = text(latest, key);
    latest = null;
  }
  return { form, payload, compare, adopt };
}
