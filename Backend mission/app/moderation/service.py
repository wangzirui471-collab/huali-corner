"""词库维护服务：运营在界面上新增 / 停用 / 启用词条，保存即热重载。

三件事必须写清楚，否则后来人会改错地方：

1. **改的是数据目录，不是仓库里的 data/*.txt。**
   内置词表随 git 走，运行时改写它，每次拉代码都要冲突一次。
   所以运营的改动落在 <数据目录>/moderation/{custom,disabled}.txt，
   由 rules.load_overrides() 在构建自动机时叠加。

2. **停用必须是一个独立列表。**
   「不再命中某条内置词」如果靠删除实现，下次更新词表它就复活了。
   disabled.txt 就是那个「黑名单的黑名单」。

3. **保存后必须 reload()。**
   自动机是进程内缓存的，不重建的话改完词条要重启服务才生效——
   运营会以为界面没保存成功。
"""
import threading
import time
from pathlib import Path

from ..core.errors import ValidationMixin
from .. import moderation as engine
from .rules import CUSTOM_FILE, DISABLED_FILE, RANK, LEVEL_NAME, load_words

# 词表文件的读改写要串行：两个运营同时点「新增」，
# 后写的那次会把前一次追加的行整段覆盖掉。
_IO = threading.RLock()


class ModerationService(ValidationMixin):

    def _overlay_dir(self):
        directory = engine.overlay()
        self.require(directory, '当前实例没有配置词库目录，无法维护词条', 500)
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --- 读 ---------------------------------------------------------------

    def moderation_words(self, u):
        """词库总览。词条可达上千条，这里一次给全，前端做本地筛选。"""
        self.admin(u)
        rs = engine.rules()
        custom = {w['word'] for w in rs.custom}
        return {
            'total': len(rs),
            'words': [{'word': w['word'], 'category': w['category'], 'level': w['level'],
                       'action': w['action'], 'source': w['source'],
                       'custom': w['word'] in custom} for w in rs.words],
            'custom_count': len(custom),
            'disabled': sorted(rs.disabled),
            'builtin_count': len(load_words()[0]),
            'skipped': [{'source': s, 'word': w, 'reason': r} for s, w, r in rs.skipped],
        }

    # --- 写 ---------------------------------------------------------------

    def add_moderation_word(self, u, d):
        """新增一条词条。若它此前被停用，这里相当于重新启用。"""
        self.admin(u)
        word = self.text(d.get('word'), 40, '词条')
        self.require(len(word) >= 2,
                     '词条至少 2 个字符：单字会大面积误伤（收了「刀」就会命中「剪刀」「水果刀」）')
        action = d.get('action') or 'block'
        self.require(action in RANK, '处置只能是 block（拦截）/ review（送审）/ report（仅记录）')
        category = str(d.get('category') or '').strip()[:20] or '运营自定义'
        level = LEVEL_NAME[action]
        with _IO:
            folder = self._overlay_dir()
            lines = self._read_lines(folder / CUSTOM_FILE)
            kept = [ln for ln in lines if ln.split('|')[0].strip() != word]
            kept.append('|'.join([word, category, level, action]))
            self._write_lines(folder / CUSTOM_FILE, kept)
            disabled = self._read_lines(folder / DISABLED_FILE)
            if word in disabled:
                self._write_lines(folder / DISABLED_FILE, [w for w in disabled if w != word])
        engine.reload()
        self._audit(u, 'wordlist_add', f'新增词条「{word}」→ {action}（{category}）')
        return {'ok': True, 'word': word, 'action': action}

    def remove_moderation_word(self, u, word):
        """停用一条词条。

        内置词条进 disabled.txt（删不掉，只能停用）；
        运营自己加的从 custom.txt 里删干净，不需要留在停用列表里。
        """
        self.admin(u)
        word = str(word or '').strip()
        self.require(word, '缺少词条')
        builtin = {w['word'] for w in load_words()[0]}
        with _IO:
            folder = self._overlay_dir()
            if word in builtin:
                disabled = self._read_lines(folder / DISABLED_FILE)
                if word not in disabled:
                    disabled.append(word)
                    self._write_lines(folder / DISABLED_FILE, disabled)
            else:
                lines = self._read_lines(folder / CUSTOM_FILE)
                left = [ln for ln in lines if ln.split('|')[0].strip() != word]
                self.require(len(left) != len(lines), '词条不存在', 404)
                self._write_lines(folder / CUSTOM_FILE, left)
                disabled = self._read_lines(folder / DISABLED_FILE)
                if word in disabled:
                    self._write_lines(folder / DISABLED_FILE, [w for w in disabled if w != word])
        engine.reload()
        self._audit(u, 'wordlist_remove', f'停用词条「{word}」')
        return {'ok': True, 'word': word}

    def restore_moderation_word(self, u, word):
        """启用一条被停用的内置词条。"""
        self.admin(u)
        word = str(word or '').strip()
        self.require(word, '缺少词条')
        with _IO:
            folder = self._overlay_dir()
            disabled = self._read_lines(folder / DISABLED_FILE)
            self.require(word in disabled, '该词条没有处于停用状态', 404)
            self._write_lines(folder / DISABLED_FILE, [w for w in disabled if w != word])
        engine.reload()
        self._audit(u, 'wordlist_restore', f'启用词条「{word}」')
        return {'ok': True, 'word': word}

    # --- 内部 -------------------------------------------------------------

    @staticmethod
    def _read_lines(path):
        if not path.is_file():
            return []
        return [ln.strip() for ln in path.read_text(encoding='utf-8', errors='replace').splitlines()
                if ln.strip() and not ln.strip().startswith('#')]

    @staticmethod
    def _write_lines(path, lines):
        # 显式 utf-8：Windows 的 open() 默认 GBK，写中文词条会直接乱码。
        path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')

    def _audit(self, u, kind, reason):
        with self.tx() as c:
            c.execute('INSERT INTO audit(actor,target,type,reason,created) VALUES(?,?,?,?,?)',
                      (u, u, kind, reason, time.time()))
