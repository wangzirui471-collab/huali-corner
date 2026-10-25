"""问答前的纯规则：敏感输入和人工意图不进入模型。"""

import re


def requires_handoff(question: str) -> str:
    """识别显式人工诉求、私密凭据及非公开上下文，返回安全理由。"""
    if re.search(r"转人工|人工客服|找客服|投诉|报警", question):
        return "需要人工核实，请先检查并提交工单。"
    sensitive = (
        r"(?i)bearer\s+\S+|sk-[a-z0-9_-]{8,}|[a-f0-9]{32,}",
        r"(?<!\d)1[3-9]\d{9}(?!\d)|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        r"密码\s*(?:是|为|[:：=])\s*\S+|恢复码\s*(?:是|为|[:：=])\s*\S+",
        r"(?i)(?:token|api[_ -]?key|password|recovery[_ -]?code)\s*[:：=]\s*\S+",
        r"私密证据|内部备注|我的订单|订单号|宿舍门牌|身份证",
    )
    if any(re.search(pattern, question) for pattern in sensitive):
        return "这类信息需要人工私下核实，已阻止发送给模型；请勿填写密码或恢复码。"
    return ""
