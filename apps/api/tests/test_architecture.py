"""防止新纯规则反向依赖 HTTP、Worker 或数据库框架。"""

import ast
import unittest
from pathlib import Path


class ArchitectureTests(unittest.TestCase):
    """检查实际存在的共享类型和领域纯规则，不生成未实现的空领域。"""

    def test_pure_modules_do_not_import_infrastructure(self) -> None:
        """按 AST 检查依赖边界，违规时报告文件与行号便于修复。"""
        root = Path(__file__).resolve().parents[1] / "src/huali"
        files = [*(root / "shared").glob("*.py"), *root.glob("modules/**/rules.py")]
        forbidden = (
            "fastapi",
            "starlette",
            "workers",
            "sqlite3",
            "pymysql",
            "huali.transport",
            "huali.infrastructure",
        )
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports = [node.module]
                for imported in imports:
                    with self.subTest(
                        path=path.name, line=node.lineno, imported=imported
                    ):
                        self.assertFalse(
                            any(
                                imported == name or imported.startswith(name + ".")
                                for name in forbidden
                            )
                        )


if __name__ == "__main__":
    unittest.main()
