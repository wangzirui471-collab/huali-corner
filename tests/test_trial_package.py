import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

class TrialPackageTests(unittest.TestCase):
    def test_source_package_has_modules_and_no_runtime_or_duplicate_flat_files(self):
        script=Path(__file__).resolve().parents[1]/'scripts/build_trial_package.py'
        spec=importlib.util.spec_from_file_location('trial_package',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'trial.zip';module.build(output)
            with zipfile.ZipFile(output) as z:
                files={name.removeprefix('zhuanjiao-trial/') for name in z.namelist()}
                for name in ['Backend mission/app/catalog/editing.py','Backend mission/app/catalog/search.py','Backend mission/server.py','web 7M/src/main.js','web 7M/src/pages/drafts.js','web 7M/miniprogram/features/catalog-search.js','start-trial.bat','package-manifest.json']:
                    self.assertIn(name,files)
                self.assertNotIn('market.py',files)
                self.assertNotIn('web/app.js',files)
                self.assertFalse(any(Path(n).suffix in ['.sqlite3','.xlsx','.db','.zip'] for n in files))
                self.assertFalse(any(any(part in ['var','var-trial','uploads','backups','.git','.env'] for part in Path(n).parts) for n in files))
                self.assertIn('Backend mission/requirements.txt',z.read('zhuanjiao-trial/start-trial.bat').decode())
                self.assertNotIn('taskkill',z.read('zhuanjiao-trial/start-trial.bat').decode().lower())
            with self.assertRaises(FileExistsError):module.build(output)
