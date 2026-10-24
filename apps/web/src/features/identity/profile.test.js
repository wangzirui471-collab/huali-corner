import { describe, it, expect } from 'vitest';
import { createProfileEditor } from './profile.js';
describe('资料版本冲突恢复', () => {
  /** 服务器对照不能覆盖用户输入；明确采用新版本后才能再次提交。 */
  it('保留输入且只按明确选择更新版本', () => {
    const editor = createProfileEditor({ id: 7, profile_version: 3, nickname: '原昵称' });
    editor.form.nickname = '未保存的输入';
    editor.compare({ id: 7, profile_version: 4, nickname: '另一标签页' });
    expect(editor.payload()).toMatchObject({ nickname: '未保存的输入', profile_version: 3 });
    editor.adopt(false);
    expect(editor.payload()).toMatchObject({ nickname: '未保存的输入', profile_version: 4 });
    expect(() => editor.compare({ id: 8, profile_version: 5 })).toThrow();
  });
});
