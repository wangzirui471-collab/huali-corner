"""把客服知识库切片、向量化，生成 index.json。

用法：
    python ai_service/ingest.py

有 Ollama 时会调用 nomic-embed-text 生成向量；没有 Ollama 时自动退化为
关键词检索（中文二元组），仍然可以跑通「检索 -> 只依据资料回答」的链路。
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# 本地 Ollama 不能走系统代理（否则 127.0.0.1 也会被代理成 502）
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


def tokenize(text):
    text = (text or '').lower()
    latin = re.findall(r'[a-z0-9_]+', text)
    zh = re.findall(r'[\u4e00-\u9fff]+', text)
    grams = []
    for run in zh:
        grams.extend(run[i:i + 2] for i in range(max(0, len(run) - 1)))
    return latin + grams


def ollama_embed(text):
    payload = {'model': config.EMBED_MODEL, 'prompt': text}
    req = urllib.request.Request(
        config.OLLAMA + '/api/embeddings',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with _NO_PROXY.open(req, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    vec = data.get('embedding')
    if not isinstance(vec, list) or not vec:
        raise ValueError('embedding 为空')
    return vec


def split_sections(text):
    """按 `##` 标题切；没有标题的文档按空行聚合成 <=700 字的块。"""
    text = text.replace('\r\n', '\n').strip()
    parts = re.split(r'(?m)^##\s+', text)
    sections = []
    intro = parts[0].strip()
    if len(intro) >= 80:
        sections.append(('概述', intro))
    for part in parts[1:]:
        lines = part.split('\n', 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ''
        if body:
            sections.append((title, body))
    if not sections:
        sections = [('全文', text)]
    return sections


def chunk_body(body, limit=700, overlap=80):
    """把长段落切成带重叠的块，避免一条 FAQ 太长被截断。"""
    body = body.strip()
    if len(body) <= limit:
        return [body]
    blocks = [b.strip() for b in re.split(r'\n\s*\n', body) if b.strip()]
    chunks, buf = [], ''
    for block in blocks:
        if len(buf) + len(block) + 1 <= limit:
            buf = (buf + '\n' + block).strip()
            continue
        if buf:
            chunks.append(buf)
        while len(block) > limit:
            chunks.append(block[:limit])
            block = block[limit - overlap:]
        buf = block
    if buf:
        chunks.append(buf)
    return chunks


def source_files():
    # 只收客户向 FAQ；内部部署、分支、凭据、运维文档一律不进知识库。
    # 曾经把 docs/TRIAL.md 等加进来，客户可能被回答「create-admin / 部署步骤」。
    return sorted((config.BASE / 'knowledge').glob('*.md'))


def main():
    chunks = []
    cid = 0
    embed_ok = config.EMBED
    embed_error = ''
    for path in source_files():
        text = path.read_text(encoding='utf-8', errors='replace')
        for title, body in split_sections(text):
            for piece in chunk_body(body):
                cid += 1
                try:
                    source = str(path.relative_to(config.ROOT))
                except ValueError:
                    source = str(path)
                item = {
                    'id': cid,
                    'title': title,
                    'source': source,
                    'text': piece,
                    'tokens': tokenize(title + '\n' + piece),
                }
                if embed_ok:
                    try:
                        item['vector'] = ollama_embed(title + '\n' + piece)
                    except Exception as exc:  # noqa: BLE001 - 连不上就整体退化
                        embed_ok = False
                        embed_error = f'{type(exc).__name__}: {exc}'
                        print(f'[warn] 向量化失败，后续改用关键词检索：{embed_error}')
                chunks.append(item)

    if embed_ok:
        # 如果前面部分成功、后面失败，已生成的向量仍保留；但为了口径一致，
        # 只要有失败就清掉全部 vector，统一走关键词，避免混用两种分数。
        if any('vector' not in c for c in chunks):
            for c in chunks:
                c.pop('vector', None)
            embed_ok = False

    index = {
        'created': time.time(),
        'chat_model': config.CHAT_MODEL,
        'embed_model': config.EMBED_MODEL,
        'embed_ok': embed_ok,
        'embed_error': embed_error,
        'chunks': chunks,
    }
    config.INDEX.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    print(f'index -> {config.INDEX}')
    print(f'chunks: {len(chunks)}  embed: {"on" if embed_ok else "off（关键词检索）"}')
    if not embed_ok and embed_error:
        print(f'提示：{embed_error}')
        print('装好 Ollama 后执行 ollama pull nomic-embed-text，再重跑本脚本即可启用向量检索。')


if __name__ == '__main__':
    main()
