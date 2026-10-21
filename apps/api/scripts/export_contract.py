"""导出服务端 OpenAPI；只实例化测试环境，不连接数据库或真实资源。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from huali.bootstrap import create_app  # noqa: E402
from huali.shared.settings import Settings  # noqa: E402


def main() -> None:
    """将稳定排序的 v1 契约写入仓库 contracts，供 Web 自动生成 DTO 类型。"""
    destination = Path(__file__).resolve().parents[3] / "contracts/openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app(Settings(environment="test")).openapi()
    destination.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
