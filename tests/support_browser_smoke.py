"""Four real browser identities exercise staff, physical returns and resale."""

import io
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import make_server


with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    market = server.market
    administrator = market.bootstrap_admin('13900000080', 'OperatorPassword2026!')
    admin_session = market.login_password('13900000080', 'OperatorPassword2026!')
    seller_session = market.register_password('13900000011', 'StudentPassword2026!', '退货卖家')
    buyer_session = market.register_password('13900000022', 'StudentPassword2026!', '退货买家')
    seller_id, buyer_id = seller_session['user']['id'], buyer_session['user']['id']
    photos = []
    for angle, color in [('front', 'red'), ('side', 'green'), ('top', 'blue')]:
        content = io.BytesIO()
        Image.new('RGB', (120, 120), color).save(content, 'PNG')
        photos.append(market.add_upload(seller_id, content.getvalue(), angle)['id'])
    draft = market.save_draft(seller_id, {'version': 0, 'fields': {
        'title': '售后测试教材', 'category': 'books', 'price': '15.00', 'photos': photos,
        'delivery': 'pickup', 'region': 'A1楼下公共入口',
    }})
    product = market.publish_draft(seller_id, draft['id'], draft['version'])
    order = market.checkout(buyer_id, {'product_ids': [product['id']], 'delivery': 'pickup', 'appointment': time.time() + 7200, 'key': 'test-order'})
    market.order_action(buyer_id, order['id'], 'pay', {})
    market.order_action(seller_id, order['id'], 'deliver', {})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])

            def page_for(session=None):
                context = browser.new_context(viewport={'width': 1100, 'height': 850})
                if session:
                    context.add_init_script('if(location.protocol==="http:")sessionStorage.setItem("hc-token",' + json.dumps(session['token']) + ')')
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
                return page

            admin = page_for(admin_session)
            admin.goto(base + '/#staff', wait_until='networkidle')
            admin.get_by_role('button', name='创建客服账号', exact=True).click(timeout=4000)
            admin.locator('[name=support_phone]').fill('13900000081')
            admin.locator('[name=support_nickname]').fill('客服甲')
            admin.locator('[name=support_password]').fill('SupportPassword2026!')
            admin.get_by_role('button', name='建立客服账号', exact=True).click()
            expect(admin.locator('[data-support-account]')).to_contain_text('客服甲')
            staff_id = market.row("SELECT id FROM users WHERE role='support'")['id']

            buyer = page_for(buyer_session)
            buyer.goto(base + '/#orders', wait_until='networkidle')
            buyer.get_by_role('button', name='申请售后', exact=True).first.click()
            buyer.locator('[name=subject]').fill('退货测试工单')
            buyer.locator('[name=body]').fill('实物已交接，申请退回核实情况')
            buyer.locator('[name=refund_mode]').select_option('return_refund')
            buyer.get_by_role('button', name='提交工单', exact=True).click()
            expect(buyer.get_by_role('heading', name='退货测试工单', exact=True)).to_be_visible()
            ticket_id = market.rows('SELECT id FROM tickets')[0]['id']
            buyer.screenshot(path='/tmp/zj-case.png', full_page=True)

            staff = page_for()
            staff.goto(base + '/#staff', wait_until='networkidle')
            staff.locator('[name=phone]').fill('13900000081')
            staff.locator('[name=password]').fill('SupportPassword2026!')
            staff.get_by_role('button', name='登录', exact=True).click()
            expect(staff.get_by_role('heading', name='客服工作台', exact=True)).to_be_visible()
            staff.get_by_text('退货测试工单', exact=True).click()
            staff.locator('[name=reason]').fill('客服认领并核实材料')
            staff.get_by_role('button', name='认领工单', exact=True).click()
            expect(staff.locator('main')).to_contain_text('处理中')
            expect(staff.get_by_role('button', name='模拟退款', exact=True)).to_have_count(0)
            staff.locator('[name=reason]').fill('建议在退回实物后退款，请管理员审批')
            staff.get_by_role('button', name='提交退款建议', exact=True).click()
            expect(staff.locator('main')).to_contain_text('待复核')

            buyer.reload(wait_until='networkidle')
            buyer.get_by_role('button', name='已退回实物', exact=True).click()
            expect(buyer.locator('main')).to_contain_text('等待卖家确认实物')
            seller = page_for(seller_session)
            seller.goto(base + '/#ticket/' + str(ticket_id), wait_until='networkidle')
            seller.get_by_role('button', name='确认收到退货', exact=True).click()
            expect(seller.locator('main')).to_contain_text('卖家已确认收到退回实物')

            admin.goto(base + '/#ticket/' + str(ticket_id), wait_until='networkidle')
            admin.locator('[name=reason]').fill('已核实收到实物，批准模拟退款')
            admin.get_by_role('button', name='模拟退款', exact=True).click()
            expect(admin.locator('main')).to_contain_text('已解决')
            assert market.order(buyer_id, order['id'])['status'] == 'refunded'

            seller.goto(base + '/#selling', wait_until='networkidle')
            seller.get_by_role('button', name='重新上架', exact=True).click()
            expect(seller.locator('[name=title]')).to_have_value('售后测试教材')
            seller.locator('[name=title]').fill('核实后重新出售的教材')
            seller.get_by_role('button', name='确认发布', exact=True).click()
            expect(seller.get_by_role('heading', name='核实后重新出售的教材', exact=True)).to_be_visible()
            assert market.order(buyer_id, order['id'])['items'][0]['title'] == '售后测试教材'

            admin.goto(base + '/#staff', wait_until='networkidle')
            admin.locator(f'[data-credit-user="{seller_id}"]').click()
            admin.locator('[name=credit_mode]').select_option('penalty')
            admin.locator('[name=ticket_id]').fill(str(ticket_id))
            admin.locator('[name=rule_key]').select_option('hidden_defect')
            admin.locator('[name=reason]').fill('与退款分开审核，核实隐瞒缺页事实')
            admin.get_by_role('button', name='记录信誉处理', exact=True).click()
            expect(admin.locator('[data-credit-row="' + str(seller_id) + '"]')).to_contain_text('85/100')
            admin.locator(f'[data-support-account="{staff_id}"] button').click()
            staff.reload(wait_until='networkidle')
            expect(staff.locator('.account-button')).to_contain_text('登录 / 注册')
            assert not errors, errors
            browser.close()
        print('Browser support provisioning, claim, refund recommendation/approval, return, resale and credit passed.')
    finally:
        server.shutdown()
        server.server_close()
