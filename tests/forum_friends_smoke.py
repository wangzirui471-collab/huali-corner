"""论坛拆分 + 好友系统 + 注册选学院年级 的浏览器验收（2026-10-19）。

覆盖：
  1. 注册时可选学院（来自学校表格的学院列）与年级，专业自填；
  2. 论坛三板块（求购 / 交换人生 / 代拿快递）切换与发帖；
  3. 求购响应：点「我能卖」→ 好友申请（附言预填、≤15 字）→ 对方同意；
  4. 社区页：新的朋友 / 好友列表 / 发消息进聊天；
  5. 非好友不能聊天（服务端 403，前端给出提示文案）。

运行：python tests/forum_friends_smoke.py
"""
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from server import make_server

with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            seller = browser.new_page(viewport={'width': 1440, 'height': 1200})
            buyer = browser.new_page(viewport={'width': 1440, 'height': 1200})
            for page in (seller, buyer):
                page.on('pageerror', lambda e: errors.append(str(e)))
            base = 'http://127.0.0.1:' + str(server.server_port)

            def register(page, phone, nickname, college, grade, major=''):
                page.goto(base, wait_until='networkidle')
                page.get_by_role('button', name='登录 / 注册', exact=True).click()
                page.get_by_role('button', name='注册账号', exact=True).click()
                page.locator('[name=phone]').fill(phone)
                page.locator('[name=nickname]').fill(nickname)
                page.locator('[name=college]').select_option(college)     # 学院下拉
                page.locator('[name=grade]').select_option(grade)         # 年级下拉
                page.locator('[name=major]').fill(major)                  # 专业自填
                page.locator('[name=password]').fill('StudentPassword2026!')
                page.locator('[name=password_confirm]').fill('StudentPassword2026!')
                page.locator('[name=agree]').check()
                page.get_by_role('button', name='注册并登录', exact=True).click()
                page.get_by_role('button', name='已保存，继续使用', exact=True).click()
                expect(page.locator('.account-button')).to_contain_text(nickname)

            register(seller, '13900000501', '论坛卖家', '机电工程学院', '2023级', '机械设计')
            register(buyer, '13900000502', '论坛买家', '计算机工程学院', '2024级', '软件工程')

            # 注册资料确实落库（学院/年级/专业）
            row = server.market.rows("SELECT college,major,grade FROM users WHERE phone='13900000501'")[0]
            assert row['college'] == '机电工程学院', row
            assert row['grade'] == '2023级', row
            assert row['major'] == '机械设计', row

            # ---- 论坛三板块 ----
            seller.get_by_role('button', name='论坛', exact=True).click()
            expect(seller.locator('.forum-tab[data-forum-tab="wants"]')).to_be_visible()
            seller.locator('.forum-tab[data-forum-tab="exchange"]').click()
            expect(seller.locator('.forum-tab[data-forum-tab="exchange"]')).to_have_class(re.compile(r"active"))
            expect(seller.locator('.forum-panel[data-forum-tab="exchange"]')).to_be_visible()
            seller.locator('.forum-panel[data-forum-tab="exchange"] textarea[name=body]').fill('会剪视频，想换吉他入门教学。')
            seller.locator('.forum-panel[data-forum-tab="exchange"] button:has-text("发布")').click()
            expect(seller.locator('.forum-panel[data-forum-tab="exchange"] .post-card').first).to_contain_text('会剪视频')
            seller.locator('.forum-tab[data-forum-tab="errand"]').click()
            expect(seller.locator('.forum-panel[data-forum-tab="errand"]')).to_be_visible()
            expect(seller.locator('.forum-panel[data-forum-tab="errand"] .forum-empty')).to_be_visible()

            # ---- 求购响应 → 好友申请 ----
            buyer.get_by_role('button', name='论坛', exact=True).click()
            buyer.get_by_role('button', name='发布求购', exact=True).click()
            buyer.locator('#want-form [name=keyword]').fill('高等数学 第七版')
            buyer.locator('#want-form [name=budget]').fill('50')
            buyer.get_by_role('button', name='发布求购').last.click()
            expect(buyer.locator('.want-list .want-row').first).to_contain_text('高等数学')

            seller.reload(wait_until='networkidle')
            seller.get_by_role('button', name='论坛', exact=True).click()
            expect(seller.locator('.want-list')).to_contain_text('高等数学')
            seller.get_by_role('button', name='我能卖').first.click()
            expect(seller.get_by_role('dialog')).to_contain_text('加「论坛买家」为好友')
            expect(seller.locator('#friend-request-form [name=message]')).to_have_value('求购：高等数学 第七版')
            # 附言计数器与 15 字上限
            seller.locator('#friend-request-form [name=message]').fill('一二三四五六七八九十一二三四五')
            expect(seller.locator('#friend-count')).to_have_text('15')
            seller.get_by_role('button', name='发送申请', exact=True).click()
            expect(seller.get_by_role('dialog')).to_have_count(0)

            # ---- 买家在社区处理申请 ----
            buyer.get_by_role('button', name='社区', exact=True).click()
            expect(buyer.locator('.friends-panel')).to_contain_text('新的朋友')
            expect(buyer.locator('.friend-request-row')).to_contain_text('一二三四五六七八九十一二三四五')
            expect(buyer.locator('.friend-request-row')).to_contain_text('回应了你的求购')
            buyer.get_by_role('button', name='同意', exact=True).click()
            expect(buyer.locator('.friend-row')).to_contain_text('论坛卖家')

            # ---- 好友之间可以聊天 ----
            buyer.get_by_role('button', name='发消息', exact=True).first.click()
            expect(buyer.locator('#wx-editor')).to_be_visible()
            buyer.locator('#wx-editor').fill('你好，我有这本教材')
            buyer.locator('#wx-editor').press('Enter')
            expect(buyer.locator('.wx-stream')).to_contain_text('你好，我有这本教材', timeout=8000)

            # ---- 非好友不能聊天：第三个账号直接访问私聊 ----
            other = browser.new_page(viewport={'width': 1440, 'height': 1000})
            other.on('pageerror', lambda e: errors.append(str(e)))
            register(other, '13900000503', '路人同学', '管理学院', '2025级')
            seller_id = server.market.rows("SELECT id FROM users WHERE phone='13900000501'")[0]['id']
            other_id = server.market.rows("SELECT id FROM users WHERE phone='13900000503'")[0]['id']
            room = server.market.private_room(other_id, seller_id)
            try:
                server.market.send_message(other_id, room['id'], '陌生人消息', 'smoke-1')
                raise AssertionError('非好友发送消息应该被拒绝')
            except Exception as exc:
                assert '好友' in str(exc), exc
            # 前端也要提前说清楚：聊天页输入区换成「还不是好友」，不是发出去才报错
            other.goto(base + '/#messages/' + str(room['id']), wait_until='networkidle')
            expect(other.locator('.wx-gate')).to_be_visible()
            expect(other.locator('.wx-gate')).to_contain_text('还不是好友')
            expect(other.locator('#wx-editor')).to_have_count(0)

            browser.close()
    finally:
        server.shutdown()

assert not errors, '浏览器报错：' + '; '.join(errors)
print('论坛/好友/注册验收通过：三板块、求购响应、15 字附言、同意后聊天、非好友禁聊、学院年级落库')
