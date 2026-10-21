"""Launcher probes real interpreters and rejects damaged offline dependencies."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import launch_trial
from launch_trial import find_ready_runtime, probe_runtime, verify_wheelhouse


class TrialLauncherTests(unittest.TestCase):
    def test_python_launcher_paths_include_spaces_and_normal_backslashes(self):
        output = (' -V:3.13 * C:\\Users\\21203\\Python313\\python.exe\n'
                  ' -V:3.12   C:\\Program Files\\Python312\\python.exe\n')
        self.assertEqual([str(path) for path in launch_trial.launcher_paths(output)],
                         [r'C:\Users\21203\Python313\python.exe',
                          r'C:\Program Files\Python312\python.exe'])

    def test_server_preserves_original_working_directory_and_database_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / 'Backend mission'
            private = backend / 'private-data'
            private.mkdir(parents=True)
            (private/'existing-data-marker').write_text('preserved')
            (backend/'server.py').write_text(
                'import os\nfrom pathlib import Path\n'
                'assert Path.cwd().samefile(Path(__file__).resolve().parent)\n'
                "assert os.environ['HUALI_DATA_DIR'] == 'private-data'\n"
                "assert (Path(os.environ['HUALI_DATA_DIR'])/'existing-data-marker').read_text() == 'preserved'\n"
                "assert os.environ['HC_DB'] == 'launcher-inheritance-test'\n")
            with patch.object(launch_trial, 'ROOT', root), patch.dict(
                    os.environ, HUALI_DATA_DIR='private-data', HC_DB='launcher-inheritance-test'):
                self.assertEqual(launch_trial.main([]), 0)

    def test_probe_reports_actual_interpreter_and_dependencies(self):
        runtime = probe_runtime(Path(sys.executable))
        self.assertIsNotNone(runtime)
        self.assertEqual(Path(runtime.executable).resolve(), Path(sys.executable).resolve())
        self.assertTrue(runtime.ready)

    def test_missing_pillow_interpreter_does_not_hide_working_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            venv.EnvBuilder(with_pip=False).create(directory)
            bare = Path(directory) / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            self.assertFalse(probe_runtime(bare).ready)
            ready = find_ready_runtime([bare, Path(sys.executable)])
            self.assertEqual(Path(ready.executable).resolve(), Path(sys.executable).resolve())

    def test_corrupt_offline_wheel_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / 'package.whl'
            wheel.write_bytes(b'original wheel bytes')
            manifest = {wheel.name: hashlib.sha256(wheel.read_bytes()).hexdigest()}
            (root / 'SHA256SUMS.json').write_text(json.dumps(manifest))
            verify_wheelhouse(root)
            wheel.write_bytes(b'corrupted bytes')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_wheelhouse(root)

    def test_check_mode_does_not_create_trial_data(self):
        project = Path(__file__).resolve().parents[1]
        data = project / 'var-trial'
        before = data.exists()
        result = subprocess.run([sys.executable, str(project/'scripts/launch_trial.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data.exists(), before)


if __name__ == '__main__':
    unittest.main()
