"""装模型之前先看清自己有什么：一条命令回答「能不能跑、该跑多大、大概多慢」。

    python ai_service/preflight.py                 # 完整体检
    python ai_service/preflight.py --ask "怎么退款"  # 顺便跑一次真实问答计时
    python ai_service/preflight.py --json          # 给脚本/监控用

退出码：0 = 模型可用；1 = 只能摘录（缺模型/没起服务）。

体检只读，不下载模型、不改配置。缺什么会直接给命令，不让人猜。
"""
import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import llm  # noqa: E402
import rag  # noqa: E402

OK, WARN, BAD = '[OK]', '[!]', '[x]'
LINES = []


def line(mark, title, detail='', advice=''):
    LINES.append({'mark': mark, 'title': title, 'detail': detail, 'advice': advice})


def gpu_name():
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=4,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return (out.stdout or '').strip().splitlines()[0] if out.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def check_python():
    v = platform.python_version()
    if sys.version_info >= (3, 8):
        line(OK, 'Python', v)
    else:
        line(BAD, 'Python', v, '需要 3.8 及以上')


def check_gpu():
    vram = llm.vram_gb()
    if vram:
        mark = OK if vram >= 6 else WARN
        line(mark, '显卡', '%s · %.1f GB 显存' % (gpu_name() or 'NVIDIA', vram),
             '' if vram >= 6 else '显存偏小，7B 会吃紧；建议用 1.5b 档，或只跑 1 位客服')
        return vram
    line(WARN, '显卡', '没检测到 NVIDIA 显卡 / 没装驱动',
         'CPU 也能跑，但 7B 大约每秒 2–4 字，只适合试用；生产建议用带独显的机器')
    return None


def check_backend():
    kind = llm.provider_kind()
    name = llm.model()
    if kind == llm.MOCK:
        line(WARN, '模型后端', '摘录模式（HC_AI_MOCK=1）', '去掉 HC_AI_MOCK 才会调用模型')
        return False
    if kind == llm.API:
        configured = bool(config.API_KEY)
        line(OK if configured else WARN, '模型后端', '远端 API · %s' % config.CHAT_MODEL,
             '' if configured else '没有 HC_AI_API_KEY，会退化为知识库摘录；要完全本地请设 HC_AI_PROVIDER=ollama')
        return configured
    if kind == llm.OPENAI:
        line(OK, '模型后端', '自建兼容端点 · %s' % config.LOCAL_URL, 'llama.cpp / vLLM / LM Studio 均可')
        return True

    tags = llm._ollama_tags()
    if tags is None:
        line(BAD, 'Ollama', '连不上 %s' % config.OLLAMA,
             '先安装并启动 Ollama（https://ollama.com/download），窗口里要能看到它常驻')
        return False
    line(OK, 'Ollama', '%s · 已装 %d 个模型' % (config.OLLAMA, len(tags)))
    installed = llm.model_installed(name)
    if installed:
        line(OK, '目标模型', name)
        return True
    line(BAD, '目标模型', '本机没有 %s' % name, 'ollama pull %s' % name)
    return False


def check_index():
    try:
        idx = rag.load_index()
    except Exception as exc:  # noqa: BLE001
        line(BAD, '知识库索引', str(exc), '先运行 python ai_service/ingest.py')
        return False
    chunks = len(idx.get('chunks') or [])
    embed = '向量检索' if idx.get('embed_ok') else '关键词检索'
    mark = OK if chunks else BAD
    line(mark, '知识库索引', '%d 条切片 · %s' % (chunks, embed),
         '' if chunks else '运行 python ai_service/ingest.py')
    return bool(chunks)


def check_concurrency(vram):
    detail = '并发 %d · 排队上限 %d · 常驻 %s' % (
        config.MAX_CONCURRENCY, config.QUEUE, config.KEEP_ALIVE)
    advice = ''
    if config.MAX_CONCURRENCY > 1 and vram and vram < 10:
        advice = '显存小于 10G 时并发 >1 会互相拖慢，建议保持 HC_AI_MAX_CONCURRENCY=1'
    line(OK, '并发设置', detail, advice)


def check_model_fit(vram):
    suggested = llm.pick_model(vram) if vram else None
    if not suggested:
        return
    current = llm.model()
    if current.split(':')[0] == suggested.split(':')[0]:
        line(OK, '档位匹配', '%.1f GB 显存 → %s' % (vram, suggested))
        return
    line(WARN, '档位不匹配', '%.1f GB 显存建议 %s，当前配置 %s' % (vram, suggested, current),
         '设 HC_AI_AUTO_MODEL=1 自动选，或 HC_AI_OLLAMA_MODEL=%s' % suggested)


def check_speed(question):
    """真跑一次，给出首字/整段耗时——比看参数表可靠。"""
    started = time.time()
    try:
        result = rag.answer(question)
    except Exception as exc:  # noqa: BLE001
        line(BAD, '试跑', '失败：%s' % type(exc).__name__, '看 server 窗口的报错，或先 ollama run 手动验证')
        return False
    ms = int((time.time() - started) * 1000)
    answer = (result.get('answer') or '').replace('\n', ' ')
    if result.get('mode') == 'llm':
        line(OK, '试跑', '%d ms · %s' % (ms, answer[:48] + ('…' if len(answer) > 48 else '')))
        return True
    line(WARN, '试跑', '%d ms · 走了降级（%s）' % (ms, result.get('mode')),
         result.get('notice') or '模型没答上来，检查上面的模型状态')
    return False


def main():
    parser = argparse.ArgumentParser(description='本地开源模型自检')
    parser.add_argument('--ask', default='', help='顺便用这个问题跑一次真实问答')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    args = parser.parse_args()

    check_python()
    vram = check_gpu()
    model_ok = check_backend()
    index_ok = check_index()
    check_concurrency(vram)
    if model_ok:
        check_model_fit(vram)

    ran = False
    if model_ok and index_ok:
        ran = check_speed(args.ask or '怎么发布商品？')

    ready = bool(model_ok and index_ok and (ran or not args.ask))
    payload = {'ready': ready, 'provider': llm.provider_kind(), 'model': llm.model(),
               'vram_gb': vram, 'checks': LINES}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print('')
        print('  转角 AI 客服 · 本地模型自检')
        print('  ' + '-' * 46)
        for item in LINES:
            print('  %-4s %-10s %s' % (item['mark'], item['title'], item['detail']))
            if item['advice']:
                print('       %s%s' % (' ' * 10, item['advice']))
        print('  ' + '-' * 46)
        if ready:
            print('  结论：可以直接启动  python ai_service/server.py')
            st = llm.status()
            if st['provider'] == llm.OLLAMA:
                print('        首个问题会慢（模型冷加载）；启动脚本已自动预热。')
        else:
            print('  结论：现在只能跑「知识库摘录」，上面标 [x] 的先按提示处理。')
        print('')
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
