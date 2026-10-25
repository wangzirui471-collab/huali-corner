"""验证线上副本补丁范围和失败关闭，不触及备份原字节。"""

import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[4]
SPEC = importlib.util.spec_from_file_location(
    "stage_stream", pathlib.Path(__file__).parents[1] / "stage_stream.py"
)


class StageTests(unittest.TestCase):
    """构建输出只允许最小旧模块变化与新增模块。"""

    def test_exact_snapshot_and_allowed_changes(self):
        """验证完整原manifest后只修改指定旧模块。"""
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as location:
            report = module.build_stage(
                ROOT / ".local-config/live-worker-5e7bd074",
                pathlib.Path(location) / "stage",
            )
            self.assertEqual(
                set(report["changed"]), {"worker.py", "app/cloudflare/ai_support.py"}
            )
            self.assertEqual(
                set(report["added"]),
                {
                    "app/cloudflare/pet_stream_core.py",
                    "app/cloudflare/pet_stream_runtime.py",
                },
            )
            self.assertEqual(report["source_modules"], 218)

    def test_patch_rejects_unknown_source(self):
        """源码漂移或重复应用必须拒绝，不能猜测锚点。"""
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.patch_ai(b"async def call_api(): pass")

    def test_refresh_preserves_local_configuration_and_rejects_tampering(self):
        """更新候选保留根任务的本机配置，若模块被改动则先停止。"""
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as location:
            target = pathlib.Path(location) / "stage"
            module.build_stage(ROOT / ".local-config/live-worker-5e7bd074", target)
            (target / "local.json").write_text("synthetic")
            module.refresh_stage(ROOT / ".local-config/live-worker-5e7bd074", target)
            self.assertEqual((target / "local.json").read_text(), "synthetic")
            (target / "modules/worker.py").write_text("tampered")
            with self.assertRaises(ValueError):
                module.refresh_stage(
                    ROOT / ".local-config/live-worker-5e7bd074", target
                )
