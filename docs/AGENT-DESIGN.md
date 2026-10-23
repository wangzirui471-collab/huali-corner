# 工作模式 Agent 设计（借鉴开源方案，不造轮子）

> 目标：让 L1 用一句话查全平台数据、完成多步操作，同时保证「模型不直接写库」。
> 本文记录我们借鉴了哪些开源做法、落地在哪、哪些故意没采用。

## 1. 借鉴清单

| 开源方案 | 借鉴的点 | 本项目落点 |
| --- | --- | --- |
| **ReAct**（Yao et al., 2022） | Reason → Act → Observation 循环，观察结果回填下一步 | `work.agent` 最多 3 步：规划器选工具 → 执行 → 把结果摘要回填 → 再规划 |
| **LangGraph**（Plan-and-Execute / HITL） | 计划与执行分离；不可逆动作中断等人确认 | 写工具只返回 `proposal` + 一次性 token；owner 在浏览器确认后才执行 |
| **OpenAI Agents SDK / Function Calling** | 工具 schema、参数校验、guardrails | `TOOLS` 目录含 title/desc/params/risk；`_validate` 先校验目标再出确认卡 |
| **DSPy** | 用少量示例固定输入输出签名，而不是堆长提示 | `PLAN_SYSTEM` 里 4 条 few-shot；不做 optimizer（没有标注集） |
| **Ragas / OpenAI Evals** | golden set、工具选择准确率、回归评测 | `tests/eval_work_agent.py`：8 条固定用例，跑工具选择与确认边界 |

## 2. 为什么不做“训练”

- 当前数据量小（几十条规则、少量操作），微调收益低于维护成本；
- 规则和工具每周都在变，微调模型跟不上；
- Cloudflare Workers 不能托管 7B/14B，线上只能走 API；
- 先用 **few-shot + 评测集** 把行为稳定下来；等积累几百条真实「问题→工具→结果」样本，再考虑：
  - 用 LoRA 微调一个小模型（本地 GPU）；
  - 或用 DSPy optimizer 自动优化提示；
  - 数据集来源：`eval_work_agent.py` + `var-trial/ai-usage.jsonl` + 人工标注。

## 3. 循环长什么样

```
用户请求
  → 先认账号动作（降级/注销/封禁/下线）→ 直接出 proposal，不调模型
  → 否则进入 ReAct 循环（最多 3 步）：
      1. /plan：把【问题 + 工具目录 + 已执行步骤摘要】给规划器
      2. 规划器返回 {"tool":"products","args":{"q":"假货"}} 或 {"tool":"final"}
      3. 读工具执行，结果摘要写回 observations
      4. 下一步可能选 product_bulk_moderate → 出确认卡
  → 模型不可用/超时 → 退回关键词规则路由
  → 写工具永远只出 proposal；确认后执行并写审计
```

示例：「把卖假货的商品全部下架」

1. 规划器选 `products`，参数 `q=假货`；
2. 执行返回候选商品；
3. 规划器看到观察结果，选 `product_bulk_moderate`，参数 `q=假货, action=delist`；
4. 后端出确认卡（最多 50 件），owner 确认后才真正下架。

## 4. 工具 schema 与权限

每个工具在 `app/support/work.py` 的 `TOOLS` 里声明：

```python
'product_bulk_moderate': {
    'title': '批量处置商品',
    'risk': 'danger',              # read / write / danger
    'desc': '按关键词/分类/卖家批量下架或恢复（最多 50 件）',
    'params': {'q': '标题关键词', 'action': 'delist/restore', 'reason': '理由'},
}
```

- `risk=read`：直接执行；
- `risk=write/danger`：`_validate` 校验目标 → 生成 proposal + HMAC token（10 分钟）→ 确认后 `_execute`；
- 所有工具 owner-only；`messages` 读也写 `chat_view` 审计；
- 手机号默认打码，`reveal=true` 看全号并写 `pii_view`。

## 5. 评测

```powershell
cd E:\zi\huali-corner-trial
.venv-trial\Scripts\python.exe tests\eval_work_agent.py
```

当前 8 条用例全部通过（工具选择 + 写操作只出 proposal）：

| 用例 | 期望工具 |
| --- | --- |
| 平台概览 | overview |
| 现在有什么需要我处理的？ | tickets |
| 查用户 godfly | users |
| 资金账本 | ledger |
| 最近有哪些举报？ | moderation |
| 把宿舍好物全部下架 | product_bulk_moderate（多步） |
| 封禁 小陈同学 | user_ban |
| 把小陈同学降为客服 | user_role |

评测用**固定 planner 桩**，不依赖网络和模型，适合 CI；真实模型的规划质量用线上 `/plan` 手工抽检。

## 6. 故意没采用的

- **LangChain / LangGraph 运行时依赖**：Workers 包体积、冷启动、Python 版本限制都不划算；
  只借鉴模式，不引入框架。
- **让模型生成 SQL**：所有查询都是参数化模板，模型只选工具和填参数。
- **自动执行写操作**：不可逆动作必须人工确认，这是硬约束。
- **微调 / 蒸馏**：见第 2 节，等样本量和稳定性到位再做。
