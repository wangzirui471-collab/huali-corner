"""Real HTTP/browser transaction alerts and public meeting-point selection."""
import json
import io
import sys
import tempfile
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import make_server
from PIL import Image

with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    seller = server.market.register_password('13900000011', 'StudentPassword2026!', '消息卖家')
    buyer = server.market.register_password('13900000022', 'StudentPassword2026!', '消息买家')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 390, 'height': 844})
            context.add_init_script('if(location.protocol==="http:")sessionStorage.setItem("hc-token",' + json.dumps(seller['token']) + ')')
            context.add_init_script("window.permissionRequests=0;if('Notification' in window){const original=Notification.requestPermission.bind(Notification);Notification.requestPermission=(...args)=>{window.permissionRequests++;return original(...args);};}")
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/#messages', wait_until='networkidle')
            expect(page.get_by_role('heading', name='订单与售后通知', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='开启浏览器提醒', exact=True)).to_be_visible()
            photos=[]
            for angle,color in [('front','red'),('side','green'),('top','blue')]:
                content=io.BytesIO()
                Image.new('RGB',(90,90),color).save(content,'PNG')
                photos.append(server.market.add_upload(seller['user']['id'],content.getvalue(),angle)['id'])
            draft=server.market.save_draft(seller['user']['id'],{'version':0,'fields':{
                'title':'带通知的教材','category':'books','price':'12.00','delivery':'both','delivery_fee':'2',
                'region':'C1楼下公共入口','photos':photos}})
            product=server.market.publish_draft(seller['user']['id'],draft['id'],draft['version'])
            order=server.market.checkout(buyer['user']['id'],{'product_ids':[product['id']],'delivery':'delivery',
                'address':'图书馆南门公共等候区','appointment':time.time()+7200,'key':'browser-order'})
            expect(page.locator('.header-message [data-notification-count]')).to_have_text('1', timeout=12000)
            page.get_by_role('button', name='刷新通知', exact=True).click()
            expect(page.locator('[data-notification-id]')).to_contain_text('有新订单')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path='/tmp/zj-notification-center.png',full_page=True)
            server.market.order_action(buyer['user']['id'],order['id'],'pay',{})
            expect(page.locator('.header-message [data-notification-count]')).to_have_text('2', timeout=12000)
            # The displayed mark-all cursor must not mark the newer, unshown payment alert read.
            page.get_by_role('button', name='全部标为已读', exact=True).click()
            expect(page.locator('.header-message [data-notification-count]')).to_have_text('1')
            page.locator('.notification-row.unread').click()
            expect(page.locator('#order-'+str(order['id']))).to_have_class('panel order-card order-focus')
            expect(page.locator('#order-'+str(order['id']))).to_contain_text('图书馆南门公共等候区')
            page.get_by_role('button',name='申请改约',exact=True).click()
            page.locator('[data-location-choice]').select_option('C2')
            page.locator('[name=address]').fill('体育馆南门公共入口')
            page.locator('[name=appointment]').fill(time.strftime('%Y-%m-%dT%H:%M',time.localtime(time.time()+10800)))
            page.get_by_role('button',name='提交给对方确认',exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
            changed=server.market.order(seller['user']['id'],order['id'])
            assert changed['changes'][0]['address']=='体育馆南门公共入口'
            assert changed['address']=='图书馆南门公共等候区', 'Pending reschedule must not replace the agreed snapshot'

            page.goto(base+'/#messages',wait_until='networkidle')
            expect(page.locator('.header-message [data-notification-count]')).to_have_count(0)
            # Browser permission must not be requested automatically or be required for inbox use.
            assert page.evaluate('permissionRequests') == 0
            page.get_by_role('button', name='开启浏览器提醒', exact=True).click()
            assert page.evaluate('permissionRequests') == 1
            page.goto(base + '/#publish/new', wait_until='networkidle')
            page.locator('[data-location-choice]').select_option('C1')
            expect(page.locator('[name=region]')).to_have_value('C1楼下公共入口')
            page.locator('[name=region]').fill('图书馆南门公共等候区')
            page.locator('[name=title]').fill('可自由填写交付地点')
            page.screenshot(path='/tmp/zj-location-selector.png',full_page=True)
            expect(page.get_by_test_id('draft-status')).to_contain_text('已保存', timeout=6000)
            page.reload(wait_until='networkidle')
            # Explicit fresh route makes a new draft, so enter the saved draft from its owner-only list.
            page.goto(base + '/#drafts', wait_until='networkidle')
            page.get_by_role('button', name='继续编辑', exact=True).first.click()
            expect(page.locator('[name=region]')).to_have_value('图书馆南门公共等候区')
            page.goto(base + '/#me', wait_until='networkidle')
            page.get_by_role('button', name='退出登录', exact=True).click()
            expect(page.locator('.account-button')).to_contain_text('登录 / 注册')
            assert page.locator('[data-notification-count]').count() == 0
            assert not errors, errors
            browser.close()
        print('Browser inbox, cross-page unread polling, read acknowledgement, opt-in permission and custom locations passed.')
    finally:
        server.shutdown()
        server.server_close()
