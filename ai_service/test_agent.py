"""agent.py 的无 key 自测：用 FunctionModel 模拟 LLM，验证工具调用全链路。

运行：python ai_service/test_agent.py
不需要 DeepSeek key、不需要主后端、不需要 GPU。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

FAKE_PRODUCTS = [
    {'id': 7, 'title': '小米充电器 65W', 'price': 45.0, 'url': '/product/7',
     'photo': '/media/up_1', 'seller': '测试同学'},
    {'id': 9, 'title': '绿联数据线', 'price': 12.5, 'url': '/product/9',
     'photo': '/media/up_2', 'seller': '小李'},
]


def fake_get(path):
    if path.startswith('/api/products'):
        return FAKE_PRODUCTS
    return {'id': 7, 'title': '小米充电器 65W', 'price': 45.0, 'photos': [{'url': '/media/up_1'}]}


def run_case(name, script):
    """script: fn(messages, info) -> ModelResponse，按剧本驱动假模型。"""
    agent._get = fake_get  # 不连主后端
    model = FunctionModel(script)
    a = Agent(model, system_prompt=agent.SYSTEM_PROMPT,
              output_type=agent.AssistantReply, retries=2)
    for tool in (agent.search_products, agent.get_product, agent.faq_lookup, agent.transfer_to_human):
        a.tool(tool)
    result = a.run_sync('测试输入')
    out = result.output
    assert isinstance(out, agent.AssistantReply), f'{name}: 输出类型错误'
    assert out.answer.strip(), f'{name}: 回答为空'
    return out


passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  ✓ {name}')
    else:
        failed += 1
        print(f'  ✗ {name} {detail}')


# 场景 1：购买意图 -> 调 search_products -> 最终回答带商品
def script_buy(messages, info):
    for m in messages:
        if isinstance(m, ModelResponse):
            for part in m.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == 'search_products':
                    return ModelResponse(parts=[TextPart(
                        content=json.dumps({
                            'answer': '找到 2 件在售的充电相关商品，看看有没有合适的。',
                            'action': 'none',
                            'products': FAKE_PRODUCTS,
                            'sources': [],
                        }, ensure_ascii=False))])
    return ModelResponse(parts=[ToolCallPart(
        tool_name='search_products', args={'query': '充电器'})])


out = run_case('购买意图链路', script_buy)
check('购买意图：回答非空', bool(out.answer))
check('购买意图：带出商品卡片', len(out.products) == 2, f'实际 {len(out.products)}')

# 场景 2：FAQ -> faq_lookup（索引不存在时返回空，链路不崩）
def script_faq(messages, info):
    for m in messages:
        if isinstance(m, ModelResponse):
            for part in m.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == 'faq_lookup':
                    return ModelResponse(parts=[TextPart(content=json.dumps({
                        'answer': '发布商品需要三张不同角度的实拍图。',
                        'action': 'none', 'products': [], 'sources': ['发布需要几张图'],
                    }, ensure_ascii=False))])
    return ModelResponse(parts=[ToolCallPart(
        tool_name='faq_lookup', args={'question': '怎么发布商品'})])


out = run_case('FAQ 链路', script_faq)
check('FAQ：回答非空', bool(out.answer))
check('FAQ：来源标注', out.sources == ['发布需要几张图'])

# 场景 3：投诉 -> 直接转人工
def script_complaint(messages, info):
    for m in messages:
        if isinstance(m, ModelResponse):
            for part in m.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == 'transfer_to_human':
                    return ModelResponse(parts=[TextPart(content=json.dumps({
                        'answer': '这个问题我暂时无法为您准确解答，马上帮您转接人工客服。',
                        'action': 'transfer_human', 'products': [], 'sources': [],
                    }, ensure_ascii=False))])
    return ModelResponse(parts=[ToolCallPart(
        tool_name='transfer_to_human', args={'reason': '用户投诉'})])


out = run_case('转人工链路', script_complaint)
check('转人工：固定兜底话术', out.answer.startswith('这个问题我暂时无法'))
check('转人工：action 标记', out.action == 'transfer_human')

# 场景 4：多轮历史转换
hist = agent.to_history([{'role': 'user', 'content': '你好'},
                         {'role': 'assistant', 'content': '在的'},
                         {'role': 'user', 'content': ''},  # 空内容应被丢弃
                         {'role': 'system', 'content': 'x'}])  # 非 user/assistant 丢弃
check('历史转换：4 条进 2 条出', len(hist) == 2, f'实际 {len(hist)}')
check('历史转换：坏输入不崩', agent.to_history('不是列表') == [])

# 场景 5：无 key 时退回旧引擎（不抛异常）
import os
saved = agent.config.API_KEY
agent.config.API_KEY = ''
r = agent.answer('测试问题')
agent.config.API_KEY = saved
check('无 key 降级：返回字典不崩', isinstance(r, dict))

print(f'\n结果：{passed} 通过，{failed} 失败')
sys.exit(1 if failed else 0)
