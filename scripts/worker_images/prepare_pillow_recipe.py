"""使用官方 Pyodide 构建配方生成指定版本的 Pillow，不修改其业务实现。"""
import json
from pathlib import Path

import yaml

VERSION = '12.3.0'
SOURCE = 'https://files.pythonhosted.org/packages/1c/3d/bb7fca845737cf9d7dbde16ed1843984665ff2e0a518f5db43e77ec540b9/pillow-12.3.0.tar.gz'
SHA256 = '3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce'


def main():
    """严格核对原配方，再仅替换正式版本、源码地址与校验值。"""
    recipe = Path('.worker-build/recipes/packages/Pillow/meta.yaml')
    data = yaml.safe_load(recipe.read_text(encoding='utf-8'))
    assert data['package']['name'] == 'Pillow'
    assert data['package']['version'] == '12.2.0'
    assert data['source']['sha256'] == 'a830b1a40919539d07806aa58e1b114df53ddd43213d9c8b75847eee6c0182b5'
    data['package']['version'] = VERSION
    data['source']['url'] = SOURCE
    data['source']['sha256'] = SHA256
    recipe.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    output = Path('.worker-build/dist')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'pillow-source.json').write_text(json.dumps({
        'version': VERSION, 'url': SOURCE, 'sha256': SHA256,
        'recipe_repository': 'https://github.com/pyodide/pyodide-recipes',
        'recipe_ref': '314-20260911', 'pyodide': '314.0.7', 'abi': 'pyemscripten_2026_0_wasm32',
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
