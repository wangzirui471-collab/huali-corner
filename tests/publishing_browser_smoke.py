"""Close/reopen real drafts, recover photos and publish once against SQLite."""

import io
import json
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import make_server


with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    session = server.market.register_password('13900000011', 'StudentPassword2026!', '草稿卖家')
    other = server.market.register_password('13900000022', 'StudentPassword2026!', '草稿买家')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            context.add_init_script('if(location.protocol==="http:")sessionStorage.setItem("hc-token",' + json.dumps(session['token']) + ')')
            context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
            page = context.new_page()
            page.goto(base + '/#publish', wait_until='networkidle')
            page.evaluate("location.hash='home'")
            expect(page.locator('#publish-form')).to_have_count(0)
            assert server.market.list_drafts(session['user']['id']) == [], 'Merely opening a form must not create empty drafts'
            page.goto(base + '/#publish', wait_until='networkidle')
            page.locator('[name=title]').fill('关窗后继续出售的数据结构')
            page.locator('[name=price]').fill('12.50')
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            for angle, color in [('front', 'red'), ('side', 'green'), ('top', 'blue')]:
                out = io.BytesIO()
                Image.new('RGB', (140, 140), color).save(out, 'PNG')
                page.locator('[name=' + angle + ']').set_input_files({
                    'name': angle + '.png', 'mimeType': 'image/png', 'buffer': out.getvalue(),
                })
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            expect(page.locator('.upload-preview img')).to_have_count(3)
            page.close()
            page = context.new_page()
            page.goto(base + '/#drafts', wait_until='networkidle')
            expect(page.locator('main')).to_contain_text('关窗后继续出售的数据结构')
            page.get_by_role('button', name='继续编辑', exact=True).click()
            expect(page.locator('[name=title]')).to_have_value('关窗后继续出售的数据结构')
            expect(page.locator('[name=price]')).to_have_value('12.50')
            expect(page.locator('.upload-preview img')).to_have_count(3)
            expect(page.locator('[name=missing]')).to_have_value('未核对，交付时检查')
            page.locator('[name=category]').select_option('living')
            expect(page.locator('.book-fields')).to_be_hidden()
            page.locator('[name=category]').select_option('books')
            expect(page.locator('.book-fields')).to_be_visible()
            page.get_by_role('button', name='确认发布', exact=True).click()
            expect(page.get_by_role('heading', name='关窗后继续出售的数据结构', exact=True)).to_be_visible()
            products = server.market.rows('SELECT * FROM products')
            assert len(products) == 1 and products[0]['price'] == 1250
            assert server.market.list_drafts(session['user']['id']) == []

            # Upload succeeds while the following cloud draft save fails.
            # Close/reopen must retain the owned upload IDs and their angles.
            page.goto(base + '/#publish/new', wait_until='networkidle')
            page.locator('[name=title]').fill('断网时已上传的照片')
            page.locator('[name=price]').fill('8')
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            offline_draft = server.market.list_drafts(session['user']['id'])[0]
            page.route('**/api/draft', lambda route: route.abort() if route.request.method == 'POST' else route.continue_())
            for angle, color in [('front', 'yellow'), ('side', 'purple'), ('top', 'orange')]:
                out = io.BytesIO()
                Image.new('RGB', (140, 140), color).save(out, 'PNG')
                page.locator('[name=' + angle + ']').set_input_files({
                    'name': angle + '.png', 'mimeType': 'image/png', 'buffer': out.getvalue(),
                })
            expect(page.locator('.upload-preview img')).to_have_count(3)
            expect(page.get_by_test_id('draft-status')).to_contain_text('同步失败', timeout=6000)
            page.close()
            page = context.new_page()
            page.goto(base + '/#publish/' + offline_draft['id'], wait_until='networkidle')
            expect(page.locator('.upload-preview img')).to_have_count(3)
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            # An unsuccessful replacement cannot silently revert to the old photo on reload.
            page.route('**/api/upload', lambda route: route.abort())
            out = io.BytesIO()
            Image.new('RGB', (140, 140), 'cyan').save(out, 'PNG')
            page.locator('[name=front]').set_input_files({'name': 'replacement.png', 'mimeType': 'image/png', 'buffer': out.getvalue()})
            expect(page.get_by_test_id('draft-status')).to_contain_text('重新选择', timeout=6000)
            page.close()
            page = context.new_page()
            page.goto(base + '/#publish/' + offline_draft['id'], wait_until='networkidle')
            expect(page.get_by_test_id('draft-status')).to_contain_text('重新选择', timeout=6000)
            page.get_by_role('button', name='确认发布', exact=True).click()
            expect(page.locator('#publish-form')).to_be_visible()
            assert len(server.market.rows('SELECT * FROM products')) == 1
            page.screenshot(path='/tmp/zj-publish.png', full_page=True)
            server.market.delete_draft(session['user']['id'], offline_draft['id'])

            # Local edits made before closing remain available if another device saved a newer version.
            stale = server.market.save_draft(session['user']['id'], {'fields': {'title': '关闭时的初版'}, 'version': 0})
            page.goto(base + '/#publish/' + stale['id'], wait_until='networkidle')
            page.locator('[name=title]').fill('本机尚未同步的修改')
            page.close()
            server.market.save_draft(session['user']['id'], {'id': stale['id'], 'version': stale['version'], 'fields': {'title': '另一台设备的新版'}})
            page = context.new_page()
            page.goto(base + '/#publish/' + stale['id'], wait_until='networkidle')
            expect(page.locator('[name=title]')).to_have_value('本机尚未同步的修改')
            expect(page.get_by_test_id('draft-status')).to_contain_text('冲突')
            page.get_by_role('button', name='另存一份', exact=True).click()
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            for saved in server.market.list_drafts(session['user']['id']):
                server.market.delete_draft(session['user']['id'], saved['id'])

            # Two open editors must not silently replace each other's changes.
            draft = server.market.save_draft(session['user']['id'], {'fields': {'title': '两个窗口'}, 'version': 0})
            page.goto(base + '/#publish/' + draft['id'], wait_until='networkidle')
            second = context.new_page()
            second.goto(base + '/#publish/' + draft['id'], wait_until='networkidle')
            page.locator('[name=title]').fill('新版窗口')
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            second.locator('[name=title]').fill('旧窗口独立内容')
            expect(second.get_by_test_id('draft-status')).to_contain_text('冲突', timeout=6000)
            assert server.market.get_draft(session['user']['id'], draft['id'])['fields']['title'] == '新版窗口'
            second.get_by_role('button', name='另存一份', exact=True).click()
            expect(second.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            assert len(server.market.list_drafts(session['user']['id'])) == 2

            buyer = browser.new_context()
            buyer.add_init_script('if(location.protocol==="http:")sessionStorage.setItem("hc-token",' + json.dumps(other['token']) + ')')
            buyer_page = buyer.new_page()
            buyer_page.goto(base + '/#drafts', wait_until='networkidle')
            expect(buyer_page.locator('main')).not_to_contain_text('新版窗口')
            page.evaluate('window.previousOperations = operationsDeps(); true')
            page.goto(base + '/#me', wait_until='networkidle')
            page.get_by_role('button', name='退出登录', exact=True).click()
            expect(page.locator('.account-button')).to_contain_text('登录 / 注册')
            assert page.evaluate('(id)=>localStorage.getItem("zj-draft-"+id)', session['user']['id']) is None
            page.evaluate('(login)=>setLogin(login)', other)
            denied = page.evaluate("async()=>{try{await previousOperations.request('/posts',{topic:'交流',body:'不应由新账号发出的旧操作'});return false;}catch{return true;}}")
            assert denied, 'An old staff/publishing context must never submit using a newly logged-in identity'
            assert not errors, errors
            browser.close()
        print('Browser draft close/reopen, private photo recovery, category choices, conflict copy and publish passed.')
    finally:
        server.shutdown()
        server.server_close()
