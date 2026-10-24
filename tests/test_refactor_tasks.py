"""在合成目录执行真实任务入口，验证显式复用本机 Python 且禁止下载解释器。"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "此任务入口仅支持 Windows PowerShell")
class RefactorSetupTests(unittest.TestCase):
    """工具安装是外部边界；用命令替身记录真实入口传递的参数和退出行为。"""

    def setUp(self):
        """准备带中文和空格的隔离项目，不读取真实库、不联网或安装依赖。"""
        self.temporary = tempfile.TemporaryDirectory(prefix="华立 setup ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        source = Path(__file__).resolve().parents[1] / "scripts/refactor.ps1"
        self.entry = scripts / source.name
        shutil.copyfile(source, self.entry)
        tools = self.root / "tools"
        tools.mkdir()
        self.log = self.root / "commands.txt"
        for name in ("uv", "npm"):
            (tools / f"{name}.cmd").write_text(
                f'@echo off\n>>"%HUALI_TEST_TOOL_LOG%" echo {name} %*\nexit /b 0\n',
                encoding="ascii",
            )
        self.environment = os.environ.copy()
        self.environment["PATH"] = str(tools) + os.pathsep + self.environment["PATH"]
        self.environment["HUALI_TEST_TOOL_LOG"] = str(self.log)
        self.python = self.root / "本机 Python" / "python.exe"
        self.python.parent.mkdir()
        self.python.touch()

    def run_setup(self, python):
        """调用真实 PowerShell 入口，保留原始退出码与诊断以便定位失败。"""
        shell = shutil.which("pwsh") or shutil.which("powershell")
        return subprocess.run(
            [
                shell,
                "-NoProfile",
                "-File",
                str(self.entry),
                "-Task",
                "Setup",
                "-PythonExecutable",
                str(python),
            ],
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_existing_python_disables_interpreter_downloads(self):
        """若入口忽略指定解释器或允许另下 Python，本例必须失败。"""
        result = self.run_setup(self.python)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.log.read_text(encoding="utf-8", errors="replace")
        self.assertIn("--no-python-downloads", commands)
        self.assertIn(str(self.python), commands)
        self.assertIn("--locked", commands)
        self.assertIn("npm --prefix", commands)

    def test_missing_python_stops_before_dependency_commands(self):
        """路径错误时不能回退到自动下载或继续安装前端。"""
        result = self.run_setup(self.root / "missing.exe")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists(), "无效解释器不得调用任何安装工具")

    def test_setup_restores_existing_uv_environment(self):
        """任务完成后不能把其他项目的缓存与解释器目录改成当前项目。"""
        wrapper = self.root / "调用后检查.ps1"
        wrapper.write_text(
            "param([string]$Entry, [string]$Python)\n"
            "& $Entry -Task Setup -PythonExecutable $Python\n"
            "@{cache=$env:UV_CACHE_DIR; python=$env:UV_PYTHON_INSTALL_DIR} | "
            "ConvertTo-Json -Compress\n",
            encoding="utf-8-sig",
        )
        self.environment["UV_CACHE_DIR"] = r"C:\existing-uv-cache"
        self.environment["UV_PYTHON_INSTALL_DIR"] = r"C:\existing-python"
        shell = shutil.which("pwsh") or shutil.which("powershell")
        result = subprocess.run(
            [
                shell,
                "-NoProfile",
                "-File",
                str(wrapper),
                str(self.entry),
                str(self.python),
            ],
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout.strip()),
            {
                "cache": r"C:\existing-uv-cache",
                "python": r"C:\existing-python",
            },
        )


if __name__ == "__main__":
    unittest.main()
