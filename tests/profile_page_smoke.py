"""个人主页视觉重做后的浏览器验收（2026-10-19）。

覆盖协作者领地但缺少浏览器覆盖的用户中心交互：
  1. 封面头部、统计条、tab（在售/已售）与 tab 切换；
  2. 编辑资料 → 保存 → 头部昵称局部刷新（userProfileSummary 契约）；
  3. 头像上传 → 预览 → 确认设为头像（隐藏按钮显形、白名单地址生效）；
  4. 空状态插画在无商品账号上出现。

运行：python tests/profile_page_smoke.py
"""
import io
import sys
import tempfile
import threading
import time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from server import make_server


def png(color):
    out = io.BytesIO()
    Image.new('RGB', (200, 200), color).save(out, 'PNG')
    return out.getvalue()


with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            seller = browser.new_page(viewport={'width': 1440, 'height': 1400})
            buyer = browser.new_page(viewport={'width': 1440, 'height': 1000})
            other = browser.new_page(viewport={'width': 1440, 'height': 1000})
            for page in (seller, buyer, other):
                page.on('pageerror', lambda e: errors.append(str(e)))
            base = 'http://127.0.0.1:' + str(server.server_port)

            def register(page, phone, nickname):
                page.goto(base, wait_until='networkidle')
                page.get_by_role('button', name='登录 / 注册', exact=True).click()
                page.get_by_role('button', name='注册账号', exact=True).click()
                page.locator('[name=phone]').fill(phone)
                page.locator('[name=nickname]').fill(nickname)
                page.locator('[name=password]').fill('StudentPassword2026!')
                page.locator('[name=password_confirm]').fill('StudentPassword2026!')
                page.locator('[name=agree]').check()
                page.get_by_role('button', name='注册并登录', exact=True).click()
                page.get_by_role('button', name='已保存，继续使用', exact=True).click()
                expect(page.locator('.account-button')).to_contain_text(nickname)

            register(seller, '13900000201', '主页卖家')
            register(buyer, '13900000202', '下单买家')
            register(other, '13900000203', '空主页同学')

            # 造一件在售 + 一件已售：已售要走完下单全流程
            seller_id = seller.evaluate("JSON.parse(sessionStorage.getItem('hc-session'))?.user?.id") \
                or server.market.rows('SELECT id FROM users WHERE phone=?', ('13900000201',))[0]['id']
            photos = [server.market.add_upload(seller_id, png(c), a)['id']
                      for a, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]
            shelf = server.market.publish(seller_id, dict(
                title='在售的英语听力收音机', category='electronics', price=2500, delivery_fee=0,
                delivery='pickup', region='A1楼下', description='九成新，听力考试同款。', photos=photos))
            sold = server.market.publish(seller_id, dict(
                title='已售的数据结构教材', category='books', price=1200, delivery_fee=0,
                delivery='pickup', region='A1楼下', description='无笔记无缺页。', photos=photos,
                edition='第二版', publisher='高教社', notes='无笔记', missing='无缺页', accessories='无附件'))
            buyer_id = server.market.rows('SELECT id FROM users WHERE phone=?', ('13900000202',))[0]['id']
            order = server.market.checkout(buyer_id, dict(
                product_ids=[sold['id']], delivery='pickup',
                appointment=time.time() + 7200, key='profile-smoke-1'))
            for action, actor in [('pay', buyer_id), ('deliver', seller_id),
                                  ('handover', buyer_id), ('receive', buyer_id)]:
                server.market.order_action(actor, order['id'], action, {})

            # ---- 自己的主页：封面 + 统计 + tab ----
            seller.get_by_role('button', name='我的', exact=True).first.click()
            seller.get_by_role('button', name='公开主页', exact=True).click()
            expect(seller.locator('.profile-hero')).to_be_visible()
            expect(seller.locator('.profile-hero-name h2')).to_have_text('主页卖家')
            expect(seller.locator('.profile-tab').first).to_contain_text('在售宝贝')
            expect(seller.locator('.profile-tab').nth(1)).to_contain_text('已售出')
            expect(seller.locator('.profile-stat').first).to_contain_text('1')       # 在售 1
            expect(seller.locator('.profile-stat').nth(1)).to_contain_text('1')      # 已售 1
            # tab 切换
            seller.locator('[data-profile-tab="sold"]').click()
            expect(seller.locator('[data-profile-tab-body="sold"]')).to_be_visible()
            expect(seller.locator('[data-profile-tab-body="sold"]')).to_contain_text('数据结构教材')
            expect(seller.locator('[data-profile-tab-body="onSale"]')).to_be_hidden()
            seller.locator('[data-profile-tab="onSale"]').click()
            expect(seller.locator('[data-profile-tab-body="onSale"]')).to_contain_text('收音机')

            # ---- 空状态插画（无商品账号）----
            other.goto(base + '/#profile/' + str(server.market.rows(
                'SELECT id FROM users WHERE phone=?', ('13900000203',))[0]['id']), wait_until='networkidle')
            expect(other.locator('[data-profile-tab-body="onSale"] .profile-empty')).to_be_visible()
            expect(other.locator('[data-profile-tab-body="onSale"] .profile-empty')).to_contain_text('看看别的同学的转角')

            # ---- 编辑资料：保存后头部局部刷新 ----
            seller.get_by_role('button', name='编辑资料', exact=True).click()
            expect(seller.locator('#user-profile-form')).to_be_visible()
            seller.locator('#user-profile-form [name=nickname]').fill('改过名的卖家')
            seller.locator('#user-profile-form [name=major]').fill('电子信息工程')
            seller.get_by_role('button', name='保存资料', exact=True).click()
            expect(seller.locator('[data-user-summary] .profile-hero-name h2')).to_have_text('改过名的卖家')
            expect(seller.locator('[data-user-summary] .profile-hero-sub')).to_contain_text('电子信息工程')

            # ---- 头像：上传 → 预览 → 确认 ----
            seller.locator('#user-avatar-file').set_input_files(
                {'name': 'avatar.png', 'mimeType': 'image/png', 'buffer': png('purple')})
            seller.get_by_role('button', name='上传并预览', exact=True).click()
            seller.get_by_role('button', name='确认设为头像', exact=True).click()
            expect(seller.locator('[data-user-summary] img[data-user-avatar-image]')).to_be_visible(
                timeout=10000)
            src = seller.locator('[data-user-summary] img[data-user-avatar-image]').get_attribute('src')
            assert src.startswith('/media/ua_'), '头像地址必须走白名单 /media/ua_*：' + src

            # ---- 别人的主页：私信按钮而非编辑 ----
            buyer.goto(base + '/#profile/' + str(seller_id), wait_until='networkidle')
            expect(buyer.get_by_role('button', name='发私信', exact=True)).to_be_visible()
            expect(buyer.get_by_role('button', name='编辑资料')).to_have_count(0)
            expect(buyer.locator('#user-profile-form')).to_have_count(0)
            expect(buyer.locator('.profile-hero-name h2')).to_have_text('改过名的卖家')

            browser.close()
    finally:
        server.shutdown()

assert not errors, '浏览器报错：' + '; '.join(errors)
print('个人主页验收通过：封面/统计/tab 切换/空状态插画/改名局部刷新/头像上传确认/他人主页只读')
