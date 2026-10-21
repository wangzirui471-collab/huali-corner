"""本地 AI 客服的配置。全部可用环境变量覆盖，默认值面向 RTX4060 8G。"""
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


# Ollama 默认地址；模型按需求选 DeepSeek-R1-Distill-Qwen-7B 的 Ollama 包
OLLAMA = os.environ.get('HC_AI_OLLAMA', 'http://127.0.0.1:11434').rstrip('/')
CHAT_MODEL = os.environ.get('HC_AI_MODEL', 'deepseek-r1:7b')
EMBED_MODEL = os.environ.get('HC_AI_EMBED_MODEL', 'nomic-embed-text')

# 检索
TOP_K = _int('HC_AI_TOP_K', 4)
MIN_SCORE = _float('HC_AI_MIN_SCORE', 0.12)
MAX_QUESTION = _int('HC_AI_MAX_QUESTION', 800)
EMBED = os.environ.get('HC_AI_EMBED', '1') != '0'

# 生成
NUM_CTX = _int('HC_AI_NUM_CTX', 4096)
NUM_PREDICT = _int('HC_AI_NUM_PREDICT', 360)
TIMEOUT = _float('HC_AI_TIMEOUT', 120)

# 运行
MOCK = os.environ.get('HC_AI_MOCK', '0') == '1'
TOKEN = os.environ.get('HC_AI_TOKEN', '')
PORT = _int('HC_AI_PORT', 8093)
INDEX = Path(os.environ.get('HC_AI_INDEX', str(BASE / 'index.json')))
