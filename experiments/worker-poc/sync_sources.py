"""将待验证的真实适配器复制到隔离 Worker，避免维护第二套图片算法。"""

import shutil
from pathlib import Path


def main() -> None:
    """仅同步白名单源码到忽略目录；不包含配置、数据库、凭据或业务入口。"""
    root = Path(__file__).resolve().parents[2]
    source = root / "apps/api/src/huali"
    destination = Path(__file__).resolve().parent / "src/huali"
    paths = (
        "__init__.py",
        "shared/__init__.py",
        "shared/errors.py",
        "infrastructure/__init__.py",
        "infrastructure/images/__init__.py",
        "infrastructure/images/normalize.py",
    )
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


if __name__ == "__main__":
    main()
