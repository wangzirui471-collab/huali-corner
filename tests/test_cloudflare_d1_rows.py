"""D1 返回值的形态兼容测试。

事故（2026-10-23）：`wrangler.jsonc` 加上 `disable_python_external_sdk` 改用平台
内置 Python SDK 后，D1 的 `.first()` 返回裸 `pyodide.ffi.JsProxy`，不再是旧外部
SDK 转换好的 dict。`dict(row)` 直接抛
`TypeError: 'pyodide.ffi.JsProxy' object is not iterable`，
于是所有查库接口 500，首页整屏「服务暂不可用」。

这里用假绑定模拟两种 SDK 的返回形态，保证读路径两种都能跑：
  · 平台 SDK：不可迭代、只有 to_py() 的代理对象
  · 旧 SDK / 本地 fake：现成的 dict
"""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

from app.cloudflare.d1 import Database, _as_dict, _as_list  # noqa: E402


class Proxy:
    """模拟 pyodide JsProxy：不能迭代、没有 dict 接口，只能 to_py()。"""

    def __init__(self, value):
        self._value = value

    def to_py(self):
        return self._value

    def __iter__(self):
        raise TypeError("'pyodide.ffi.JsProxy' object is not iterable")


class Statement:
    def __init__(self, binding, sql):
        self.binding = binding
        self.sql = sql

    def bind(self, *params):
        self.binding.params = params
        return self

    async def all(self):
        return SimpleNamespace(results=self.binding.rows)

    async def first(self):
        return self.binding.row

    async def run(self):
        return SimpleNamespace(meta=Proxy({'changes': 1, 'size_after': 2048}))


class Binding:
    """最小 D1 绑定替身。"""

    def __init__(self, rows, row=None):
        self.rows = rows
        self.row = row
        self.params = ()

    def prepare(self, sql):
        return Statement(self, sql)

    async def batch(self, statements):
        return Proxy([SimpleNamespace(meta={'changes': 1}) for _ in statements])


class RowsTest(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_proxy_rows_are_converted(self):
        db = Database(Binding(
            rows=Proxy([Proxy({'id': 7, 'title': '台灯'})]),
            row=Proxy({'n': 3}),
        ))
        self.assertEqual(self.run_async(db.all('SELECT 1')), [{'id': 7, 'title': '台灯'}])
        self.assertEqual(self.run_async(db.first('SELECT 1')), {'n': 3})
        self.assertEqual(self.run_async(db.scalar('SELECT 1')), 3)

    def test_plain_dict_rows_still_work(self):
        db = Database(Binding(rows=[{'id': 1}], row={'n': 2}))
        self.assertEqual(self.run_async(db.all('SELECT 1')), [{'id': 1}])
        self.assertEqual(self.run_async(db.scalar('SELECT 1')), 2)

    def test_no_rows_is_empty_not_error(self):
        db = Database(Binding(rows=None, row=None))
        self.assertEqual(self.run_async(db.all('SELECT 1')), [])
        self.assertEqual(self.run_async(db.scalar('SELECT 1')), None)

    def test_meta_changes_and_size_are_converted(self):
        db = Database(Binding(rows=[]))
        self.assertEqual(Database.expect(self.run_async(db.run('UPDATE 1')), 'x'), 1)
        self.assertEqual(self.run_async(db.used_bytes()), 2048)

    def test_batch_returns_python_list(self):
        db = Database(Binding(rows=[]))
        results = self.run_async(db.batch([('SELECT 1', ()), ('SELECT 2', ())]))
        self.assertEqual(len(results), 2)
        self.assertIsInstance(results, list)

    def test_helpers_tolerate_both_shapes(self):
        self.assertEqual(_as_dict(Proxy({'a': 1})), {'a': 1})
        self.assertIsNone(_as_dict(None))
        self.assertEqual(_as_list(Proxy([1, 2])), [1, 2])
        self.assertEqual(_as_list(None), [])


if __name__ == '__main__':
    unittest.main()
