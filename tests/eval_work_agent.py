"""工作模式 Agent 评测（golden set）。

借鉴 OpenAI Evals / Ragas 的思路：不训练模型，用固定用例回归
「工具选择是否正确、写操作是否只出 proposal、多步任务能否衔接」。
运行：
    .venv-trial\\Scripts\\python.exe tests\\eval_work_agent.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))

import app.support.ai as ai
from app.market import Market

CASES = [
    {'q': '平台概览', 'plan': [{'tool': 'overview', 'args': {}}], 'expect': 'overview'},
    {'q': '现在有什么需要我处理的？', 'plan': [{'tool': 'tickets', 'args': {'status': 'open'}}], 'expect': 'tickets'},
    {'q': '查用户 godfly', 'plan': [{'tool': 'users', 'args': {'q': 'godfly'}}], 'expect': 'users'},
    {'q': '资金账本', 'plan': [{'tool': 'ledger', 'args': {}}], 'expect': 'ledger'},
    {'q': '最近有哪些举报？', 'plan': [{'tool': 'moderation', 'args': {}}], 'expect': 'moderation'},
    {'q': '把宿舍好物全部下架',
     'plan': [{'tool': 'products', 'args': {'q': '宿舍'}},
              {'tool': 'product_bulk_moderate', 'args': {'q': '宿舍', 'action': 'delist', 'reason': '评测'}}],
     'expect': 'product_bulk_moderate', 'proposal': True},
    {'q': '封禁 小陈同学', 'plan': None, 'expect': 'user_ban', 'proposal': True},
    {'q': '把小陈同学降为客服', 'plan': None, 'expect': 'user_role', 'proposal': True},
    {'q': '发布 3 件宿舍好物演示商品',
     'plan': [{'tool': 'demo_generate', 'args': {'prompt': '宿舍好物', 'count': 3}},
              {'tool': 'demo_publish', 'args': {}}],
     'expect': 'demo_publish', 'proposal': True},
]


def main():
    root = Path(tempfile.mkdtemp(prefix='hc-eval-'))
    m = Market(str(root))
    owner = m.login('13800000001', m.request_code('13800000001')['demo_code'])['user']['id']
    target = m.login('13800000002', m.request_code('13800000002')['demo_code'])['user']['id']
    with m.tx() as c:
        c.execute("UPDATE users SET role='owner' WHERE id=?", (owner,))
    m.create_ticket(target, {'type': 'other', 'subject': '评测工单', 'body': '用于 Agent 评测'})

    original = ai.plan
    rows = []
    passed = 0
    for case in CASES:
        script = case.get('plan')
        if script:
            def fake(question, tools, history=None, _script=script):
                idx = min(len(history or []), len(_script) - 1)
                return _script[idx]
            ai.plan = fake
        else:
            ai.plan = lambda question, tools, history=None: {'tool': 'overview', 'args': {}}
        try:
            result = m.work_chat(owner, case['q'])
            actual = (result.get('proposal') or {}).get('tool') or result.get('tool')
            ok = actual == case['expect']
            if case.get('proposal'):
                ok = ok and bool(result.get('proposal')) and bool(result.get('token'))
        except Exception as exc:  # noqa: BLE001
            actual = 'ERROR: %s' % exc
            ok = False
        passed += 1 if ok else 0
        rows.append((case['q'], case['expect'], actual, ok))

    ai.plan = original
    print('| 用例 | 期望工具 | 实际工具 | 结果 |')
    print('| --- | --- | --- | --- |')
    for q, expect, actual, ok in rows:
        print('| %s | `%s` | `%s` | %s |' % (q, expect, actual, 'PASS' if ok else 'FAIL'))
    total = len(rows)
    print('\n工具选择/确认边界：%d/%d = %.1f%%' % (passed, total, passed * 100.0 / total))
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
