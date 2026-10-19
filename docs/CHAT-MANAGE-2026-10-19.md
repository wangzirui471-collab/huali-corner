# 2026-10-19 · 消息页三项缺失功能

## 背景

用户反馈消息页三个问题：

1. 屏蔽了对方后没办法取消——只能「屏蔽对方」单向按钮，没有 toggle 入口。
2. 「删除聊天记录」找不到——目前右键单条消息只能「删除」单条，整段会话没法清。
3. 「置顶」会话没有入口——重要会话会被新消息挤到下面去。

## 改动范围

### 数据库（`Backend mission/app/core/database.py`）

新增 `room_pins(user_id, room_id, pinned_at)` 表，SQLite 与 MySQL 双 schema 都补上：

```sql
CREATE TABLE IF NOT EXISTS room_pins(
  user_id INTEGER, room_id INTEGER, pinned_at REAL,
  PRIMARY KEY(user_id, room_id));
```

「(user_id, room_id) 主键」+ 写时 INSERT OR REPLACE 即可，置顶/取消都幂等。

### 同步后端（`Backend mission/app/community/service.py`）

- `rooms(u)`：每条 joined 房补 `pinned`、`pinned_at`、`blocked`、`peer_id` 四个字段；
  - `pinned`/`pinned_at` 走 `room_pins` 子查询；
  - `blocked` 只对 `kind='private'` 计算（看 `blocks` 表里我有没有屏蔽对方）；
  - 列表按 `(置顶, pinned_at 倒序, last_at 倒序, id 倒序)` 排序，置顶永远在前。
- 新增 `pin_room(u, rid, pinned)`：必须是房间成员才能置顶（防止给陌生人群加塞）。
- 新增 `clear_room(u, rid)`：把当前用户在该房间的所有「未隐藏、未归档」消息批量写入 `message_hides`，
  顺手把 `members.last_read_id` 拨到当下——避免「记录没了，角标还在」。
- `block(u, target, enabled)` 早就支持双向，无需改；前端改成 toggle 调用即可。

### 同步路由（`Backend mission/server.py`）

- `POST /api/rooms/pin` → `m.pin_room(u, room_id, pinned)`
- `POST /api/rooms/clear` → `m.clear_room(u, room_id)`

### Worker 端（`Backend mission/app/cloudflare/community_api.py`）

- `cf_community_rooms` 同步加入 `pinned_at` 子查询、pinned/blocked/peer_id 字段、
  排序逻辑，staff 池也补字段（pinned=False, blocked=False, peer_id=0）。
- 新增 `cf_pin_room` 与 `cf_clear_room`，路由表挂上 `/api/rooms/pin`、`/api/rooms/clear`。

### 前端（`web 7M/src/pages/messages.js` + `actions/social.js` + `core/dom.js` + `market.css`）

- `roomItem(r, activeId)` 在每行增加：
  - 置顶时标题前一个细钉子图标（`icon('pin')`），行底加浅黄背景，肉眼可辨。
  - 私聊里「我屏蔽了对方」时显示 🚫 小标。
  - 行尾的「…」按钮：桌面 hover 才出现，手机常显。点击/长按/右键都开上下文菜单。
- 上下文菜单（`openRoomMenu`）：
  - 「置顶会话 / 取消置顶」—— 私聊、群聊、客服会话都有；
  - 「删除聊天记录」—— 全员都有，先 confirm 确认（只清自己这半边，对方不受影响）；
  - 「屏蔽对方 / 取消屏蔽」—— 仅私聊显示，群聊/总聊/客服不显示（屏蔽语义只对单条私聊生效）。
- `roomAction(kind, id, …args)`：所有会话级操作（置顶、清记录、屏蔽切换）走统一入口，
  失败 toast，成功后主动重拉 /rooms 并刷新列表；如果当前打开的就是这个房间，整页 `go` 一次刷新头/底。
- 聊天窗头部「屏蔽对方」按钮改为 toggle，文案随 `room.blocked` 切换；
  屏蔽时在输入区上方多一条常驻 banner「已屏蔽对方，对方不能继续发消息」+ inline「取消屏蔽」按钮，
  避免「对方不回我以为是 ta 不在线」其实是屏蔽了。
- 长按 / 右键会话列表项也开同样的上下文菜单（手机没有 hover，「…」按钮用户未必发现）。
- 排序：去掉前端的 `sort((a,b) => b.last_at - a.last_at)`，因为后端已经按置顶 + 最近消息排好了；
  前端再排会把置顶甩回原位。

### CSS（`web 7M/market.css`）

- `.wx-room.pinned` —— 浅黄背景；
- `.wx-room-pin` —— 标题前的细钉子；
- `.wx-room-blocked` —— 屏蔽小标；
- `.wx-room-more` —— 「…」按钮（桌面 hover 才显，手机常显）；
- `.wx-blocked-banner` —— 聊天窗底部的常驻屏蔽提示。

### 图标（`web 7M/src/core/dom.js`）

`icons` 字典新增 `more: 'M5 12h.01M12 12h.01M19 12h.01'`。

## 测试

新增 `tests/test_room_manage.py`，5 项：

1. 置顶 toggle round-trip：置顶后 rooms[0] 是它，取消置顶回到原顺序。
2. 删除聊天记录只影响自己：自己 `messages` 为空，对方仍能拉到 3 条。
3. 群聊里 `blocked` 永远是 `false`，群聊也支持置顶。
4. 屏蔽 toggle 写库后 rooms() 立刻反映 `blocked`。
5. 非成员不能 pin/clear 别人的房间。

`tests/test_message_receipts`、`tests/test_defect_fixes`、`tests/test_content_removal`、`tests/test_admin_chat_view`、
`tests/test_cloudflare_community` 一起跑全过。

## 端到端冒烟（试用版 8083）

- 注册 alice2/bob2 → 私聊 → 置顶 ✓ → `rooms` 里 `pinned: true, blocked: false, peer_id: 10` ✓
- 屏蔽 ✓ → `blocked: true` ✓ → 取消屏蔽 ✓ → `blocked: false` ✓
- 删聊天记录 ✓ → A 端 0 条，B 端仍 3 条 ✓
- 取消置顶 ✓
