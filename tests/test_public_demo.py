import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PublicDemoTests(unittest.TestCase):
    def build(self, output):
        return subprocess.run(
            [sys.executable, str(ROOT/'scripts/build_public_demo.py'), '--output', str(output)],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_export_contains_only_static_seeded_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'site'
            result=self.build(output)
            self.assertEqual(result.returncode,0,result.stderr)
            # 用 as_posix：Windows 下 relative_to 会给出 src\main.js，跟断言里的斜杠对不上。
            files=[p.relative_to(output) for p in output.rglob('*') if p.is_file()]
            self.assertTrue({'index.html','src/main.js','public-demo.js','demo-data.json','_headers'}.issubset({p.as_posix() for p in files}))
            self.assertFalse(any(p.suffix in {'.py','.sqlite3','.xlsx','.zip'} or 'var' in p.parts for p in files))
            data=json.loads((output/'demo-data.json').read_text(encoding='utf-8'))
            self.assertTrue(data['config']['public_demo'])
            self.assertEqual(len(data['products']),13)
            self.assertTrue(all(p['simulation'] for p in data['products']))
            raw=json.dumps(data,ensure_ascii=False)
            for forbidden in ['phone','token','138000000','uploads/','proof','market.sqlite3']:
                self.assertNotIn(forbidden,raw)
            self.assertNotIn('role',raw)
            html=(output/'index.html').read_text(encoding='utf-8')
            # 演示快照必须先于主模块执行，否则 api() 拿不到 window.hualiDemoApi。
            self.assertLess(html.index('public-demo.js'),html.index('src/main.js'))

    def test_export_does_not_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'site';output.mkdir()
            sentinel=output/'keep.txt';sentinel.write_text('keep')
            result=self.build(output)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(sentinel.read_text(),'keep')
            self.assertFalse((output/'index.html').exists())

    def test_export_does_not_write_source_artwork(self):
        sys.path.insert(0,str(ROOT/'Backend mission'))
        from scripts.build_public_demo import build
        write_text=Path.write_text
        def protected_write(path,*args,**kwargs):
            self.assertNotIn(ROOT/'web 7M/assets',path.parents,'Export must not modify source artwork')
            return write_text(path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,patch.object(Path,'write_text',protected_write):
            build(Path(tmp)/'site')


if __name__=='__main__':unittest.main()
