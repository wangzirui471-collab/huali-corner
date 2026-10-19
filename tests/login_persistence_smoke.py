"""登录持久化验收（2026-10-19 用户要求「电脑上登录过就不用再登录」）。

模拟「关掉浏览器再打开」：登录后导出 storage_state（含 localStorage），
在全新 context 里用它恢复，验证免登录；退出登录后同样的恢复方式应回到游客。
"""
import sys
import tempfile
import threading
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
            base = 'http://127.0.0.1:' + str(server.server_port)

            ctx = browser.new_context()
            page = ctx.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base, wait_until='networkidle')
            page.get_by_role('button', name='登录 / 注册', exact=True).click()
            page.get_by_role('button', name='注册账号', exact=True).click()
            page.locator('[name=phone]').fill('13900000801')
            page.locator('[name=nickname]').fill('记住我同学')
            page.locator('[name=college]').select_option('计算机工程学院')
            page.locator('[name=grade]').select_option('2023级')
            page.locator('[name=password]').fill('StudentPassword2026!')
            page.locator('[name=password_confirm]').fill('StudentPassword2026!')
            page.locator('[name=agree]').check()
            page.get_by_role('button', name='注册并登录', exact=True).click()
            page.get_by_role('button', name='已保存，继续使用', exact=True).click()
            expect(page.locator('.account-button')).to_contain_text('记住我同学')

            # 令牌必须落在 localStorage（关浏览器仍保留），且 sessionStorage 不再留副本
            stored = page.evaluate("({local: localStorage.getItem('hc-token'), session: sessionStorage.getItem('hc-token')})")
            assert stored['local'], '登录后 localStorage 应保存 hc-token'
            assert stored['session'] is None, '迁移后 sessionStorage 不应再留副本'

            state = ctx.storage_state()          # 相当于「关浏览器」时磁盘上的状态
            ctx.close()

            # ---- 全新 context + 恢复存储 = 重新打开浏览器 ----
            ctx2 = browser.new_context(storage_state=state)
            page2 = ctx2.new_page()
            page2.on('pageerror', lambda e: errors.append(str(e)))
            page2.goto(base, wait_until='networkidle')
            page2.wait_for_timeout(800)
            expect(page2.locator('.account-button')).to_contain_text('记住我同学')   # 免登录
            # 直接打开个人主页也应正常（token 恢复后接口可用）
            me_id = server.market.rows("SELECT id FROM users WHERE phone='13900000801'")[0]['id']
            page2.goto(base + '/#profile/' + str(me_id), wait_until='networkidle')
            expect(page2.locator('.profile-hero-name h2')).to_have_text('记住我同学')
            expect(page2.get_by_role('button', name='编辑资料', exact=True)).to_be_visible()

            # ---- 退出登录后，本地令牌必须清干净 ----
            page2.goto(base + '/#me', wait_until='networkidle')
            page2.get_by_role('button', name='退出登录', exact=True).click()
            page2.wait_for_timeout(600)
            after = page2.evaluate("({local: localStorage.getItem('hc-token'), session: sessionStorage.getItem('hc-token')})")
            assert after['local'] is None, '退出登录应清掉 localStorage 令牌'
            assert after['session'] is None
            expect(page2.locator('.account-button')).to_contain_text('登录 / 注册')
            state2 = ctx2.storage_state()
            ctx2.close()

            # 用「退出后」的状态重开，仍是游客
            ctx3 = browser.new_context(storage_state=state2)
            page3 = ctx3.new_page()
            page3.goto(base, wait_until='networkidle')
            page3.wait_for_timeout(600)
            expect(page3.locator('.account-button')).to_contain_text('登录 / 注册')
            ctx3.close()

            browser.close()
    finally:
        server.shutdown()

assert not errors, '浏览器报错：' + '; '.join(errors)
print('登录持久化验收通过：关浏览器重开免登录、令牌只在 localStorage、退出登录后回到游客')
