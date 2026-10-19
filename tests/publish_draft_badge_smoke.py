"""F-02 / F-04 / F-03 浏览器验收：分类字段、草稿恢复、首页停留角标刷新。

- F-04：发布页第 04 步按分类显示字段，切换分类即时更换，不出现书籍字段串类。
- F-02：发布中途离开再回来，弹「恢复草稿」；恢复后文字字段原样回来；
        丢弃后不再弹；照片不进草稿（恢复后仍需重选，只提示不阻塞）。
- F-03：卖家停留在首页不切换路由，买家下单后 ≤25 秒内「我的」角标自己出现。

运行：python tests/publish_draft_badge_smoke.py （Windows 使用 Playwright 自带 Chromium）
"""
import io
import sys
import tempfile
import threading
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from server import make_server


def png(color):
    out = io.BytesIO()
    Image.new('RGB', (180, 180), color).save(out, 'PNG')
    return out.getvalue()


with tempfile.TemporaryDirectory() as root:
    server = make_server(root, 0, trial=True)
    server.market.bootstrap_admin('13900000099', 'OperatorPassword2026!')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()          # Windows/macOS/Linux 均用 Playwright 自带 Chromium
            seller = browser.new_page(viewport={'width': 1440, 'height': 1000})
            buyer = browser.new_page(viewport={'width': 1440, 'height': 1000})
            for page in (seller, buyer):
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

            register(seller, '13900000101', 'F04卖家')
            register(buyer, '13900000102', 'F03买家')

            # ---- F-04：分类字段 ----
            seller.get_by_role('button', name='发布闲置', exact=True).first.click()
            expect(seller.locator('[name=edition]')).to_be_visible()          # 默认二手书：版次在
            expect(seller.locator('[name=publisher]')).to_be_visible()
            seller.locator('.cat-option', has_text='电子产品').click()      # 切到电子产品
            expect(seller.locator('[name=brand]')).to_be_visible()
            expect(seller.locator('[name=model]')).to_be_visible()
            expect(seller.locator('[name=edition]')).to_have_count(0)         # 书籍字段必须消失
            expect(seller.locator('[name=publisher]')).to_have_count(0)
            expect(seller.locator('[name=notes]')).to_have_count(0)
            expect(seller.locator('#cat-fields-title')).to_have_text('数码参数')
            seller.locator('.cat-option', has_text='运动闲置').click()
            expect(seller.locator('[name=size]')).to_be_visible()             # 尺码／规格
            expect(seller.locator('[name=edition]')).to_have_count(0)
            expect(seller.locator('#cat-fields-title')).to_have_text('装备信息')
            seller.locator('.cat-option', has_text='二手书').click()         # 切回
            expect(seller.locator('[name=edition]')).to_be_visible()

            # ---- F-02：草稿恢复 / 丢弃 ----
            seller.locator('.cat-option', has_text='电子产品').click()      # 当前是二手书，先切回电子产品
            seller.locator('[name=title]').fill('罗技 K380 键盘 九成新')
            seller.locator('textarea[name=description]').fill('F02 草稿测试：蓝牙键盘，功能正常。')
            seller.locator('[name=brand]').fill('罗技')
            seller.locator('[name=model]').fill('K380')
            seller.wait_for_timeout(900)                                    # 等过 500ms 防抖落盘
            seller.get_by_role('button', name='逛逛', exact=True).first.click()   # 离开发布页
            expect(seller.locator('[name=title]')).to_have_count(0)
            seller.get_by_role('button', name='发布闲置', exact=True).first.click()  # 再回来
            expect(seller.get_by_role('dialog')).to_contain_text('恢复未发布完的内容')
            seller.get_by_role('button', name='恢复草稿').click()
            expect(seller.locator('[name=title]')).to_have_value('罗技 K380 键盘 九成新')
            expect(seller.locator('textarea[name=description]')).to_have_value('F02 草稿测试：蓝牙键盘，功能正常。')
            expect(seller.locator('[name=model]')).to_have_value('K380')
            seller.get_by_role('button', name='逛逛', exact=True).first.click()
            seller.get_by_role('button', name='发布闲置', exact=True).first.click()
            expect(seller.get_by_role('dialog')).to_contain_text('恢复未发布完的内容')  # 草稿仍在（未发布不自动清）
            seller.get_by_role('button', name='丢弃').click()
            seller.get_by_role('button', name='逛逛', exact=True).first.click()
            seller.get_by_role('button', name='发布闲置', exact=True).first.click()
            expect(seller.get_by_role('dialog')).to_have_count(0)              # 丢弃后不再弹

            # ---- F-03：停留首页，角标自己刷新 ----
            seller.get_by_role('button', name='逛逛', exact=True).first.click()
            seller_user = server.market.rows('SELECT id FROM users WHERE phone=?', ('13900000101',))[0]['id']
            uploads = [server.market.add_upload(seller_user, png(c), a)['id']
                       for a, c in zip(['front', 'side', 'top'], ['red', 'green', 'blue'])]
            data = '{"photos":[{"url":"/media/' + uploads[0] + '","angle":"front"}],"edition":"第一版"}'
            with server.market.connect() as c:
                c.execute("INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,status,data,created)"
                          " VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (seller_user, 'F03 角标测试', 'books', 900, 0, 'pickup', 'A1楼下', 'available',
                           data, __import__('time').time()))
                pid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            buyer.goto(base + '/#product/' + str(pid), wait_until='networkidle')
            buyer.get_by_role('button', name='加入取货清单', exact=True).click()
            buyer.get_by_role('button', name='取货清单', exact=False).first.click()
            buyer.locator('[name=appointment]').fill(
                __import__('time').strftime('%Y-%m-%dT%H:%M', __import__('time').localtime(__import__('time').time() + 7200)))
            buyer.get_by_role('button', name='生成模拟订单', exact=True).click()
            # 卖家停在首页不动：角标应在 25 秒内自己出现（不切换路由）
            expect(seller.locator('[data-nav-badge="me"]').first).to_have_text('1', timeout=30000)
            browser.close()
    finally:
        server.shutdown()

assert not errors, '浏览器报错：' + '; '.join(errors)
print('F-02 / F-04 / F-03 浏览器验收通过：分类字段、草稿恢复/丢弃、首页停留角标刷新')
