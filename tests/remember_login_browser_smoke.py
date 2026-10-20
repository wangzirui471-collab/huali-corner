"""Real browser restart test with isolated accounts, database and browser profile."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))
from server import make_server

with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as profile:
    server=make_server(data,0,trial=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    server.market.register_password('13900000991','remember-test','记住登录测试')
    base=f'http://127.0.0.1:{server.server_port}'
    errors=[]
    try:
        with sync_playwright() as p:
            def launch():
                c=p.chromium.launch_persistent_context(profile,headless=True,
                    executable_path=os.environ.get('CHROME_PATH',r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
                c.on('page',lambda page:page.on('pageerror',lambda e:errors.append(str(e))))
                return c
            context=launch();page=context.pages[0]
            def login():
                page.goto(base,wait_until='networkidle')
                page.get_by_role('button',name='登录 / 注册',exact=True).click()
                page.locator('#login-form [name=phone]').fill('13900000991')
                page.locator('#login-form [name=password]').fill('remember-test')
                page.get_by_role('button',name='登录',exact=True).click()
                expect(page.locator('.account-button')).to_contain_text('记住登录测试')
            login()
            assert page.evaluate("!!localStorage.getItem('hc-token')")
            context.close()
            context=launch();page=context.pages[0]
            page.goto(base,wait_until='networkidle')
            expect(page.locator('.account-button')).to_contain_text('记住登录测试')
            assert page.url.rstrip('/').endswith(str(server.server_port)) or page.url.endswith('#home')
            print('PASS: full browser close/reopen restores authenticated home')
            page.route('**/api/me',lambda route:route.fulfill(status=503,body='<html>temporary</html>',content_type='text/html'))
            page.reload(wait_until='networkidle')
            expect(page.locator('#app')).to_contain_text('服务暂不可用')
            assert page.evaluate("!!localStorage.getItem('hc-token')")
            page.unroute('**/api/me');page.reload(wait_until='networkidle')
            expect(page.locator('.account-button')).to_contain_text('记住登录测试')
            print('PASS: service failure preserves remembered login')
            second=context.new_page();second.goto(base+'/#me',wait_until='networkidle')
            page.goto(base+'/#me',wait_until='networkidle')
            page.get_by_role('button',name='退出登录',exact=True).click()
            expect(page.get_by_role('button',name='登录 / 注册',exact=True)).to_be_visible()
            expect(second.get_by_role('button',name='登录 / 注册',exact=True)).to_be_visible()
            context.close();context=launch();page=context.pages[0]
            page.goto(base,wait_until='networkidle')
            expect(page.get_by_role('button',name='登录 / 注册',exact=True)).to_be_visible()
            print('PASS: explicit logout clears cache in all tabs and after restart')
            login()
            with server.market.tx() as c:c.execute('DELETE FROM sessions')
            page.reload(wait_until='networkidle')
            expect(page.get_by_role('button',name='登录 / 注册',exact=True)).to_be_visible()
            assert page.evaluate("localStorage.getItem('hc-token')") is None
            print('PASS: revoked server session clears persistent cache')
            context.close()
            assert not errors,errors
    finally:
        server.shutdown();server.server_close()
