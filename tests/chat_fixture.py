"""私聊测试公共前置：先把好友关系走到 accepted，再建私聊会话。

为什么需要这个模块：
  `send_message` 里有好友门禁（`Backend mission/app/community/service.py:399`）——
  「先加对方为好友才能聊天」。这不是缺陷，是产品要求：陌生人不能直接私聊。
  但很多用例（撤回、仅自己删除、已读回执、会话管理、管理端查看）只关心
  消息层的行为，顺手建一个 private_room 就发消息，于是被门禁拦下报错。

  正确做法是补测试前置，而不是把门禁删掉把测试刷绿。门禁本身仍由
  非好友负向用例守着（见 `assert_gate_blocks_stranger` 的调用方）。

用法：
    from chat_fixture import befriend, private_chat
    befriend(self.m, self.a, self.b)              # 只建好友关系
    room = private_chat(self.m, self.a, self.b)   # 建好友 + 建私聊，返回 room_id
"""


def befriend(m, requester, target):
    """让 requester 申请、target 接受，返回 friendships.id。

    走的是真实接口（friend_request -> friend_decide），不直接写库，
    这样前置本身也顺带覆盖了申请/同意链路。
    """
    m.friend_request(requester, target)
    row = m.row("SELECT id FROM friendships WHERE requester=? AND target=? AND status='pending'",
                (requester, target))
    assert row, '好友申请没有落库，前置失败'
    m.friend_decide(target, row['id'], True)
    return row['id']


def private_chat(m, a, b):
    """建好友 + 建私聊，返回 room_id。给只关心消息层的用例用。"""
    befriend(m, a, b)
    return m.private_room(a, b)['id']
