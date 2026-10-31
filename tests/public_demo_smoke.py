"""Serve only exported files, without the Python application or its database."""
import functools
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

with tempfile.TemporaryDirectory() as tmp:
    site=Path(tmp)/'preview'
    subprocess.run([sys.executable,str(ROOT/'scripts/build_public_demo.py'),'--output',str(site)],check=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=tmp))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    errors=[];requests=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':390,'height':844})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append((request.method,request.url)))
            base='http://127.0.0.1:'+str(server.server_port)+'/preview/'
            page.goto(base,wait_until='networkidle')
            expect(page.locator('.product-card')).to_have_count(9)
            expect(page.locator('.simulation-bar')).to_contain_text('公开演示')
            page.get_by_role('button',name='二手书',exact=True).first.click()
            expect(page.locator('.product-card')).to_have_count(6)
            page.get_by_role('searchbox',name='搜索商品').fill('Python')
            page.locator('#search-form').get_by_role('button',name='搜索',exact=True).click()
            expect(page.locator('.product-card')).to_have_count(1)
            page.locator('.card-title').click()
            expect(page.get_by_role('heading',name='Python程序设计',exact=True)).to_be_visible()
            page.get_by_role('button',name='加入取货清单',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('不收集')
            expect(page.locator('#overlay input,#overlay textarea')).to_have_count(0)
            page.get_by_role('button',name='关闭',exact=True).click()
            page.locator('.seller-box').click()
            expect(page.locator('.profile-card')).to_contain_text('林同学')
            page.goto(base+'#community',wait_until='networkidle')
            expect(page.locator('.post-card')).to_have_count(2)
            expect(page.locator('textarea')).to_have_count(0)
            page.get_by_role('button',name='评论 / 回复',exact=False).first.click()
            expect(page.get_by_role('dialog')).to_be_visible()
            expect(page.locator('#comment-form')).to_have_count(0)
            page.get_by_role('button',name='关闭',exact=True).click()
            for route in ['publish','orders','messages','me','support','staff','cart','favorites','ticket/1']:
                page.goto(base+'#'+route,wait_until='networkidle')
                expect(page.locator('[data-public-demo-feature]')).to_be_visible()
                expect(page.locator('input[type=tel],[name=address],input[type=file],textarea')).to_have_count(0)
            page.goto(base,wait_until='networkidle')
            page.get_by_role('button',name='登录 / 注册',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('不收集')
            expect(page.locator('#login-form')).to_have_count(0)
            page.get_by_role('button',name='关闭',exact=True).click()
            for width in [375,390,768,1440]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
            assert not errors,errors
            assert all(method=='GET' and '/api/' not in url for method,url in requests),requests
            page.screenshot(path='/tmp/huali-public-demo.png',full_page=True)
            browser.close()
        print('Static demo passed: subpath hosting, search, details, profiles, community, guarded features; no API requests or write requests; responsive layouts.')
    finally:server.shutdown();server.server_close()
