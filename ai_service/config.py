"""本地 AI 客服的配置。默认外接 DeepSeek API，全部可用环境变量覆盖。"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# provider: api（外接 DeepSeek）| ollama（本机开源模型）| openai_local（自建 OpenAI
# 兼容端点：llama.cpp / vLLM / LM Studio）| mock（只摘录知识库）
# 别名 local / selfhost 等价于 ollama。详见 docs/AI-LOCAL-MODEL.md。
PROVIDER = os.environ.get('HC_AI_PROVIDER', 'api').strip().lower()

# DeepSeek 官方 OpenAI 兼容接口；模型名 deepseek-flash 即 DeepSeek-V4.1-Flash
API_URL = os.environ.get('HC_AI_API_URL', 'https://api.deepseek.com/chat/completions')
API_KEY = os.environ.get('HC_AI_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
CHAT_MODEL = os.environ.get('HC_AI_MODEL', 'deepseek-flash')
OWNER_MODEL = os.environ.get('HC_AI_MODEL_OWNER') or CHAT_MODEL
OWNER_API_URL = os.environ.get('HC_AI_API_URL_OWNER') or API_URL
OWNER_API_KEY = os.environ.get('HC_AI_API_KEY_OWNER') or API_KEY
# L1 办公助手可以单独走后端：客户问答跑本机小模型，批量草稿走云端强模型。
# 留空 = 跟主后端一致。
OWNER_PROVIDER = os.environ.get('HC_AI_OWNER_PROVIDER', '').strip().lower()

# 可选：本地 Ollama 模式（deepseek-r1:7b = DeepSeek-R1-Distill-Qwen-7B 的 Q4_K_M）
OLLAMA = os.environ.get('HC_AI_OLLAMA', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_MODEL = os.environ.get('HC_AI_OLLAMA_MODEL', 'deepseek-r1:7b')
EMBED_MODEL = os.environ.get('HC_AI_EMBED_MODEL', 'nomic-embed-text')
# 按显存自动选模型（12G+ → 14b，6G+ → 7b，其余 → 1.5b）
AUTO_MODEL = os.environ.get('HC_AI_AUTO_MODEL', '1') != '0'
# 模型常驻显存：不设的话每个问题前都要重新加载 5–15 秒
KEEP_ALIVE = os.environ.get('HC_AI_KEEP_ALIVE', '30m')

# 自建 OpenAI 兼容端点（llama.cpp / vLLM / LM Studio），可无 Key
LOCAL_URL = os.environ.get('HC_AI_LOCAL_URL', 'http://127.0.0.1:8080/v1/chat/completions')
LOCAL_KEY = os.environ.get('HC_AI_LOCAL_KEY', '')
LOCAL_MODEL = os.environ.get('HC_AI_LOCAL_MODEL', '')

# 并发与排队：8G 显存跑 7B，并发 >1 只会互相拖慢，默认串行。
# 排满 QUEUE 个后立刻返回「忙」（Retry-After），不把请求堆到超时。
MAX_CONCURRENCY = _int('HC_AI_MAX_CONCURRENCY', 1)
QUEUE = _int('HC_AI_QUEUE', 3)
QUEUE_TIMEOUT = _float('HC_AI_QUEUE_TIMEOUT', 45)
QUEUE_RETRY_AFTER = _int('HC_AI_QUEUE_RETRY_AFTER', 5)
# 本地小模型的输出上限：给太大只会拖到超时，回答也被 trim 截断
LOCAL_MAX_PREDICT = _int('HC_AI_LOCAL_MAX_PREDICT', 700)
WARMUP = os.environ.get('HC_AI_WARMUP', '1') != '0'

# 检索
TOP_K = _int('HC_AI_TOP_K', 4)
MIN_SCORE = _float('HC_AI_MIN_SCORE', 0.12)
MAX_QUESTION = _int('HC_AI_MAX_QUESTION', 800)
# 默认关键词检索（40 条 FAQ 足够）；要向量检索再开 HC_AI_EMBED=1
EMBED = os.environ.get('HC_AI_EMBED', '0') != '0'

# 生成
NUM_CTX = _int('HC_AI_NUM_CTX', 4096)
NUM_PREDICT = _int('HC_AI_NUM_PREDICT', 360)
TIMEOUT = _float('HC_AI_TIMEOUT', 60)

# 运行
MOCK = os.environ.get('HC_AI_MOCK', '0') == '1'
TOKEN = os.environ.get('HC_AI_TOKEN', '')
PORT = _int('HC_AI_PORT', 8093)
INDEX = Path(os.environ.get('HC_AI_INDEX', str(BASE / 'index.json')))
