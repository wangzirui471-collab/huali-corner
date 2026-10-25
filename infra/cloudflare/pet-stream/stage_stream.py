"""仅由指定线上原字节备份构建候选目录；校验全部模块且绝不原地覆盖。"""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

AI_SHA256 = "6d584aea4c0bd3f69c6108a91d6c07d515dfb704b622e7cad4c89dc4d9e80b36"
ENTRY_SHA256 = (
    "c47becc891d5f4caa61fef8b88c8905c955dafaE7540251d65a7652cd8534600".lower()
)
SOURCE = Path(__file__).parent / "source"


def digest(value):
    """计算原始字节SHA256，避免换行或编码改变被遗漏。"""
    return hashlib.sha256(value).hexdigest()


def unique_replace(value, old, new):
    """锚点必须唯一；漂移或重复应用直接终止构建。"""
    if value.count(old) != 1:
        raise ValueError("补丁锚点不唯一或已改变")
    return value.replace(old, new, 1)


def patch_ai(original):
    """只注入请求局部模型hook和流调用预留额度，旧入口保留原行为。"""
    if digest(original) != AI_SHA256:
        raise ValueError("ai_support不是已审阅的线上原字节版本")
    newline = b"\r\n" if b"\r\n" in original else b"\n"

    def encoded(text):
        """使新增片段使用原模块换行，不改动其他任何原字节。"""
        return text.encode().replace(b"\n", newline)

    start = original.index(b"async def call_api(")
    anchor = original.index(b"    api_key = getattr(env, 'HC_AI_API_KEY'", start)
    hook = encoded(
        "    # 请求局部流hook；未设置时继续原非流供应商路径。\n    from .pet_stream_core import current_stream\n    stream = current_stream.get()\n    if stream is not None:\n        return await stream.model(question, context, env, history, open_mode)\n"
    )
    result = original[:anchor] + hook + original[anchor:]
    start = result.index(b"    async def ai_chat(self, request):")
    end = result.index(b"    async def ai_reply(", start)
    block = result[start:end]
    old = encoded("        await self.ai_quota(uid)\n")
    new = old + encoded(
        "        # 流调用在模型开始前预留原额度；规则回答不扣，取消也不绕额。\n        from .pet_stream_core import current_stream\n        stream = current_stream.get()\n        if stream is not None:\n            stream.set_charge(self.ai_count, uid)\n"
    )
    block = unique_replace(block, old, new)
    block = unique_replace(
        block,
        encoded("        if result.get('mode') == 'llm':"),
        encoded(
            "        if result.get('mode') == 'llm' and not (stream is not None and stream.charged):"
        ),
    )
    result = result[:start] + block + result[end:]
    compile(result, "ai_support.py", "exec")
    return result


def build_stage(snapshot, target):
    """全部输入摘要核对成功后创建新候选，输出逐模块变化清单。"""
    snapshot, target = Path(snapshot).resolve(), Path(target).resolve()
    modules = snapshot / "modules"
    if target.exists() or target == snapshot or snapshot in target.parents:
        raise ValueError("候选目录必须不存在且不能位于原备份内")
    manifest = json.loads(
        (snapshot / "module-manifest.json").read_text(encoding="utf-8-sig")
    )
    if len(manifest) != 218:
        raise ValueError("线上module数量与已审阅版本不同")
    expected = {item["name"]: item for item in manifest}
    actual = {
        path.relative_to(modules).as_posix()
        for path in modules.rglob("*")
        if path.is_file()
    }
    if actual != set(expected):
        raise ValueError("线上modules目录存在遗漏或额外文件")
    for name, item in expected.items():
        data = (modules / name).read_bytes()
        if digest(data) != item["sha256"] or len(data) != item["bytes"]:
            raise ValueError("线上备份模块摘要不匹配：" + name)
    if digest((modules / "worker.py").read_bytes()) != ENTRY_SHA256:
        raise ValueError("Worker入口不是已审阅原版本")
    patched = patch_ai((modules / "app/cloudflare/ai_support.py").read_bytes())
    shutil.copytree(modules, target / "modules")
    changes = {
        "worker.py": (SOURCE / "worker.py").read_bytes(),
        "app/cloudflare/ai_support.py": patched,
    }
    additions = {
        f"app/cloudflare/{name}": (SOURCE / name).read_bytes()
        for name in ("pet_stream_core.py", "pet_stream_runtime.py")
    }
    for name, data in (changes | additions).items():
        (target / "modules" / name).write_bytes(data)
    output = []
    for path in sorted((target / "modules").rglob("*")):
        if path.is_file():
            name = path.relative_to(target / "modules").as_posix()
            data = path.read_bytes()
            output.append(
                {
                    "name": name,
                    "sha256": digest(data),
                    "bytes": len(data),
                    "type": expected.get(name, {}).get("type", "text/x-python"),
                }
            )
    report = {
        "source_version": "5e7bd074-0fe4-42ba-887a-2f5347a7479e",
        "source_modules": len(manifest),
        "changed": sorted(changes),
        "added": sorted(additions),
        "unchanged": len(manifest) - len(changes),
        "modules": output,
    }
    (target / "stream-stage-manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    """接收备份与新输出目录，构建可由根任务审阅的候选。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="校验已有候选后只更新四个模块，保留本地配置",
    )
    args = parser.parse_args()
    report = (
        refresh_stage(args.snapshot, args.target)
        if args.refresh
        else build_stage(args.snapshot, args.target)
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "modules"},
            ensure_ascii=False,
        )
    )


def refresh_stage(snapshot, target):
    """摘要验证已有候选后只更新允许模块，保留本机配置和测试状态。"""
    target = Path(target).resolve()
    previous = json.loads(
        (target / "stream-stage-manifest.json").read_text(encoding="utf-8")
    )
    if previous["source_version"] != "5e7bd074-0fe4-42ba-887a-2f5347a7479e":
        raise ValueError("候选来源版本不匹配")
    for item in previous["modules"]:
        path = target / "modules" / item["name"]
        if digest(path.read_bytes()) != item["sha256"]:
            raise ValueError("候选模块存在未登记修改：" + item["name"])
    with tempfile.TemporaryDirectory() as location:
        staged = Path(location) / "candidate"
        report = build_stage(snapshot, staged)
        for name in report["changed"] + report["added"]:
            shutil.copyfile(staged / "modules" / name, target / "modules" / name)
        shutil.copyfile(
            staged / "stream-stage-manifest.json", target / "stream-stage-manifest.json"
        )
    return report


if __name__ == "__main__":
    main()
