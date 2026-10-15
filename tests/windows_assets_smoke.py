"""Exercise Chromium while Windows associates .js files with text/plain."""
import mimetypes
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import make_server

guess_type=mimetypes.guess_type
def windows_mime_type(path,*args,**kwargs):
    if str(path).lower().endswith('.js'):return 'text/plain',None
    return guess_type(path,*args,**kwargs)

with tempfile.TemporaryDirectory() as root,patch('server.mimetypes.guess_type',windows_mime_type):
    server=make_server(root,0,trial=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    errors=[];console=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            page=browser.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda message:console.append(message.text) if message.type=='error' else None)
            page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
            try:expect(page.locator('.market-app')).to_be_visible()
            except AssertionError:
                print('Visible page:',page.locator('body').inner_text())
                print('Browser errors:',console)
                raise
            expect(page.locator('.simulation-bar')).to_contain_text('计算机工程学院试用')
            page.get_by_role('button',name='登录 / 注册',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('手机号未验证')
            assert not errors,errors
            assert not any('MIME' in message for message in console),console
            browser.close()
        print('Windows MIME regression passed: trial homepage and password login load despite OS .js=text/plain; nosniff remains enabled.')
    finally:server.shutdown();server.server_close()
