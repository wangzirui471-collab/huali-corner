"""开源框架版 AI 助手（PydanticAI，MIT 许可）。

为什么换框架
------------
分支上的 `rag.py` 用纯标准库手写了意图判断、检索、DeepSeek 调用循环和
兜底——能跑，但每个能力都要自己维护。PydanticAI（20.8k stars，MIT）
把这些都做成了框架能力：function calling、多轮记忆、结构化输出、
模型可替换（OpenAI 兼容即可接 DeepSeek，以后换模型不改业务代码）。

工具集借鉴 NVIDIA-AI-Blueprints/retail-shopping-assistant 的零售助手：
    search_products / get_product / add_to_cart / transfer_to_human
FAQ 知识库检索保留本项目的实现（复用 ingest.py 生成的 index.json）。

行为规范沿用 docs/AI-SUPPORT.md：只依据资料回答、资料不足固定兜底、
不承诺优惠赔付、不输出思维链、300 字内。这些是产品规则，不因换框架改变。

引擎切换：HC_AI_ENGINE=agent（默认，有 key 时）/ legacy（旧 rag.py）/
mock。没有 API key 时自动退回 mock，不会把报错抛给用户。
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import config

try:
    from pydantic_ai import Agent, RunContext, UnexpectedModelBehavior
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    _HAS_FRAMEWORK = True
except ImportError:  # pragma: no cover - 没装框架时 server 会退回 legacy
    _HAS_FRAMEWORK = False

BACKEND = config.BACKEND
TIMEOUT = min(config.TIMEOUT, 20)

SYSTEM_PROMPT = """你是「华立转角」校园二手平台的 AI 小助手，名字叫小转。
你是客服的辅助工具，不是自动回复机器人。遵守以下规则：

1. 意图判断：打招呼或闲聊 → 简短回应，不调用工具；明确说「转人工/找客服」→ 调用 transfer_to_human；投诉、差评、强烈不满 → 调用 transfer_to_human。
2. 想买东西（「有没有/想买/找一下 X」）→ 调用 search_products；问某个商品详情 → 调用 get_product。
3. 平台规则、流程、售后问题 → 先调用 faq_lookup 查知识库，只依据检索到的内容回答。
4. 只依据工具返回的资料回答，资料没写的不许用常识补全；不承诺优惠、赔付、封号结果；不用「大概、可能」这类不确定表述。
5. 资料不足或检索为空 → 一字不差地回复：「这个问题我暂时无法为您准确解答，马上帮您转接人工客服。」并调用 transfer_to_human。
6. 回答控制在 300 字内，语气像同学之间说话，不要思维过程和 Markdown 标题。
7. 不要询问或记录手机号、宿舍号等隐私信息。"""


# ---- 结构化输出 ------------------------------------------------------------

if _HAS_FRAMEWORK:

    @dataclass
    class ProductCard:
        id: int
        title: str
        price: float
        url: str = ''

    @dataclass
    class AssistantReply:
        """给前端的回复。products 非空时前端渲染商品卡片。"""
        answer: str
        action: str = 'none'          # none | transfer_human | open_product
        products: list = field(default_factory=list)
        sources: list = field(default_factory=list)


# ---- 工具实现 --------------------------------------------------------------

def _get(path):
    """调主后端（/api/products、/api/product）。ai_service 不直接连数据库，
    后端在本地还是云端都对它透明。"""
    url = BACKEND + path
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))


def search_products(query, category=None, max_price=None) -> list:
    """按关键词搜在售商品。返回最多 4 条的简要列表。"""
    try:
        params = ['limit=40']
        if query:
            params.append('q=' + urllib.request.quote(query))
        if category:
            params.append('category=' + urllib.request.quote(category))
        items = _get('/api/products?' + '&'.join(params))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    out = []
    for p in items:
        try:
            if float(p.get('price') or 0) > float(max_price or 1e12):
                continue
        except (TypeError, ValueError):
            pass
        photos = p.get('photos') or []
        out.append({
            'id': p.get('id'),
            'title': p.get('title') or '',
            'price': p.get('price') or 0,
            'url': '/product/' + str(p.get('id')),
            'photo': (photos[0].get('url') if photos and isinstance(photos[0], dict) else ''),
            'seller': p.get('nickname') or '',
        })
        if len(out) >= 4:
            break
    return out


def get_product(product_id) -> dict:
    """查单个商品详情。"""
    try:
        return _get('/api/product?id=' + str(int(product_id)))
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        return {}


def faq_lookup(question) -> list:
    """检索本项目 FAQ 知识库（index.json 由 ingest.py 生成）。"""
    try:
        import rag
        idx = rag.load_index()
        hits = rag.retrieve(question, k=config.TOP_K)
        return [{'question': h.get('question', ''), 'answer': h.get('answer', ''),
                 'score': round(float(h.get('score') or 0), 3)} for h in hits]
    except Exception:  # noqa: BLE001 - 索引缺失时知识库降级为空
        return []


def transfer_to_human(reason='') -> dict:
    """标记转人工。前端收到 action=transfer_human 时展示工单入口。"""
    return {'transferred': True, 'reason': reason}


# ---- agent 组装 ------------------------------------------------------------

def build_agent():
    """组装 PydanticAI agent。模型走 OpenAI 兼容通道，DeepSeek 官方即兼容。"""
    if not _HAS_FRAMEWORK:
        raise RuntimeError('pydantic-ai 未安装')
    base = config.API_URL.replace('/chat/completions', '') or 'https://api.deepseek.com/v1'
    provider = OpenAIProvider(base_url=base, api_key=config.API_KEY or 'not-needed')
    model = OpenAIChatModel(config.CHAT_MODEL, provider=provider)
    agent = Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        output_type=AssistantReply,
        retries=2,
    )
    agent.tool(search_products)
    agent.tool(get_product)
    agent.tool(faq_lookup)
    agent.tool(transfer_to_human)
    return agent


def to_history(raw):
    """把前端传来的 [{role, content}] 转成框架的消息对象；失败就丢掉记忆。

    直接构造 ModelRequest/ModelResponse，不走 JSON adapter——各版本的
    序列化格式有差异，对象构造最稳。只保留最近 10 条，控制 token。
    """
    if not isinstance(raw, list) or not raw:
        return []
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    out = []
    for m in raw[-10:]:
        if not isinstance(m, dict):
            continue
        role, content = m.get('role'), str(m.get('content') or '').strip()
        if not content:
            continue
        if role == 'user':
            out.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == 'assistant':
            out.append(ModelResponse(parts=[TextPart(content=content)]))
    return out


def answer(question, history=None):
    """统一入口：无框架或无 key 时退回旧实现，行为可预期。"""
    if not _HAS_FRAMEWORK or not config.API_KEY or config.MOCK:
        try:
            import rag
            return rag.answer(question)
        except Exception:  # noqa: BLE001 - 旧引擎/索引缺失时同样只给兜底
            return {
                'answer': '这个问题我暂时无法为您准确解答，马上帮您转接人工客服。',
                'action': 'transfer_human',
                'products': [],
                'sources': [],
            }
    agent = build_agent()
    try:
        result = agent.run_sync(question, message_history=to_history(history))
    except Exception as exc:  # noqa: BLE001 - 模型侧任何错误都不抛给用户
        return {
            'answer': '这个问题我暂时无法为您准确解答，马上帮您转接人工客服。',
            'action': 'transfer_human',
            'products': [],
            'sources': [],
            'error': type(exc).__name__,
        }
    reply = result.output
    return {
        'answer': reply.answer,
        'action': reply.action,
        'products': [vars(p) if hasattr(p, '__dataclass_fields__') else p
                     for p in (reply.products or [])],
        'sources': reply.sources or [],
        'mode': 'agent',
    }
