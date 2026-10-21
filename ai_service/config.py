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


# provider: api（外接 DeepSeek）| ollama（本地模型）| mock（只摘录知识库）
PROVIDER = os.environ.get('HC_AI_PROVIDER', 'api').strip().lower()

# DeepSeek 官方 OpenAI 兼容接口；模型名 deepseek-flash 即 DeepSeek-V4.1-Flash
API_URL = os.environ.get('HC_AI_API_URL', 'https://api.deepseek.com/chat/completions')
API_KEY = os.environ.get('HC_AI_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
CHAT_MODEL = os.environ.get('HC_AI_MODEL', 'deepseek-flash')

# 可选：本地 Ollama 模式
OLLAMA = os.environ.get('HC_AI_OLLAMA', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_MODEL = os.environ.get('HC_AI_OLLAMA_MODEL', 'deepseek-r1:7b')
EMBED_MODEL = os.environ.get('HC_AI_EMBED_MODEL', 'nomic-embed-text')

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
