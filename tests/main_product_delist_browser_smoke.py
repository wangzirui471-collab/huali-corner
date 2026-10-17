"""Main-branch UI: staff can remove a listing from detail and home using its existing API."""
import io
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
from server import make_server


def run():
    with tempfile.TemporaryDirectory() as directory:
        server = make_server(directory, 0, trial=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        market = server.market
        admin = market.bootstrap_admin('13900009710', 'OperatorPassword2026!')
        administrator = market.login_password('13900009710', 'OperatorPassword2026!')
        market.create_staff(admin['id'], dict(phone='13900009711', password='WorkerPassword2026!', nickname='测试客服', role='support'))
        support = market.login_password('13900009711', 'WorkerPassword2026!')
        seller = market.register_password('13900009712', 'SellerPassword2026!', '测试卖家')

        def listing(title, owner=None):
            uid = owner or seller['user']['id']
            photos = []
            for angle, color in [('front', 'red'), ('side', 'green'), ('top', 'blue')]:
                image = io.BytesIO()
                Image.new('RGB', (64, 64), color).save(image, 'PNG')
                photos.append(market.add_upload(uid, image.getvalue(), angle)['id'])
            return market.publish(uid, dict(title=title, category='books', price=1200, delivery_fee=0,
                delivery='pickup', region='C1楼下', description='教材实拍，无缺页', photos=photos,
                edition='第七版', publisher='教材出版社', notes='少量', missing='无缺页', accessories='无附件'))['id']

        detail_ids = [listing('详情管理员核查教材'), listing('详情客服核查教材')]
        home_ids = [listing('首页管理员核查教材'), listing('首页客服核查教材')]
        keep = listing('保留展示教材')
        own = listing('管理员自有教材', admin['id'])
        seller_own = listing('用户自主下架教材')
        seller_home = listing('用户首页下架教材')
        support_own = listing('客服自主下架教材', support['user']['id'])
        foreign_live = listing('他人的在售教材', admin['id'])
        base = 'http://127.0.0.1:' + str(server.server_port)
        errors = []
        requests = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])

                def page_for(session):
                    page = browser.new_page(viewport={'width':1440, 'height':1000})
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: requests.append(request.url) if request.method == 'POST' else None)
                    if session:
                        import json
                        page.add_init_script('sessionStorage.setItem("hc-token",' + json.dumps(session['token']) + ');')
                    page.goto(base + '/#home', wait_until='networkidle')
                    return page

                a, w, s, guest = [page_for(session) for session in [administrator, support, seller, None]]
                expect(a.locator('.desktop-navigation')).to_contain_text('管理员工作台')
                expect(a.locator('.brand-text')).to_contain_text('华立转角')
                expect(guest.get_by_role('button', name='下架商品', exact=True)).to_have_count(0)
                for page in [s, guest]:
                    page.goto(base + '/#product/' + str(keep), wait_until='networkidle')
                    expect(page.locator('.detail-info h1')).to_have_text('保留展示教材')
                    expect(page.locator('[data-action="moderate-product"]')).to_have_count(0)
                    expect(page.locator('[data-action="delist"]')).to_have_count(1 if page == s else 0)
                for page, pid in zip([a, w], detail_ids):
                    page.goto(base + '/#product/' + str(pid), wait_until='networkidle')
                    expect(page.locator('.detail-info h1')).to_have_text(market.product(pid)['title'])
                    button = page.locator('.detail-info').get_by_role('button', name='下架商品', exact=True)
                    expect(button).to_be_visible()
                    assert button.evaluate('(el)=>getComputedStyle(el).color') == 'rgb(185, 28, 28)'
                    button.click()
                    expect(page.locator('#moderate-form')).to_be_visible()
                    page.get_by_role('button', name='关闭', exact=True).click()
                    assert market.product(pid)['status'] == 'available'
                    button.click()
                    page.locator('#moderate-form [name=reason]').fill('核实描述与实拍不一致')
                    page.get_by_role('button', name='确认下架', exact=True).click()
                    expect(page.locator('.detail-info > .tag')).to_contain_text('已下架')
                    expect(page.locator('.detail-info [data-action="moderate-product"]')).to_have_count(0)
                    assert market.row('SELECT delisted_by FROM products WHERE id=?', (pid,))['delisted_by'] in [admin['id'], support['user']['id']]
                for page, pid in zip([a, w], home_ids):
                    page.goto(base + '/#home', wait_until='networkidle')
                    card = page.locator('.product-card').filter(has=page.get_by_role('button', name=market.product(pid)['title'], exact=True))
                    button = card.get_by_role('button', name='下架商品', exact=True)
                    expect(button).to_be_visible()
                    button.click()
                    assert page.url.endswith('#home')
                    page.locator('#moderate-form [name=reason]').fill('首页核查描述不符')
                    page.get_by_role('button', name='确认下架', exact=True).click()
                    expect(card).to_have_count(0)
                a.goto(base + '/#product/' + str(own), wait_until='networkidle')
                expect(a.locator('.detail-info h1')).to_have_text('管理员自有教材')
                a.get_by_role('button', name='下架商品', exact=True).click()
                s.goto(base + '/#product/' + str(own), wait_until='networkidle')
                expect(s.locator('.detail-info h1')).to_have_text('管理员自有教材')
                expect(s.get_by_role('button', name='下架商品', exact=True)).to_have_count(0)
                a.locator('#moderate-form [name=reason]').fill('管理员下架自己的商品')
                a.get_by_role('button', name='确认下架', exact=True).click()
                expect(a.locator('.detail-info > .tag')).to_contain_text('已下架')
                for page, pid in [(s,seller_own),(w,support_own)]:
                    page.goto(base + '/#product/' + str(pid), wait_until='networkidle')
                    expect(page.locator('.detail-info h1')).to_have_text(market.product(pid)['title'])
                    button=page.get_by_role('button',name='下架商品',exact=True)
                    expect(button).to_have_attribute('data-action','delist')
                    page.once('dialog',lambda dialog:dialog.dismiss())
                    button.click()
                    assert market.product(pid)['status']=='available'
                    page.once('dialog',lambda dialog:dialog.accept())
                    button.click()
                    expect(page.locator('.detail-info > .tag')).to_contain_text('已下架')
                    assert market.row('SELECT delisted_by FROM products WHERE id=?',(pid,))['delisted_by']==0
                s.goto(base+'/#home',wait_until='networkidle')
                card=s.locator('.product-card').filter(has=s.get_by_role('button',name='用户首页下架教材',exact=True))
                expect(card.locator('[data-action="delist"]')).to_be_visible()
                foreign=s.locator('.product-card').filter(has=s.get_by_role('button',name='他人的在售教材',exact=True))
                expect(foreign.get_by_role('button',name='下架商品',exact=True)).to_have_count(0)
                expect(s.locator('[data-action="moderate-product"]')).to_have_count(0)
                s.once('dialog',lambda dialog:dialog.accept())
                card.locator('[data-action="delist"]').click()
                expect(card).to_have_count(0)
                a.goto(base + '/#product/' + str(keep), wait_until='networkidle')
                expect(a.locator('.detail-info h1')).to_have_text('保留展示教材')
                Path('/tmp/zj-main-delist').mkdir(exist_ok=True)
                a.locator('.detail-info .detail-actions').last.screenshot(path='/tmp/zj-main-delist/detail-actions.png')
                for width in [375, 390, 768, 1440]:
                    a.set_viewport_size({'width':width, 'height':900})
                    assert a.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert any(url.endswith('/api/product/moderate') for url in requests)
                assert not any(url.endswith('/api/product/moderation') for url in requests)
                assert not errors, errors
                assert market.profile(seller['user']['id'])['score'] == 100
                browser.close()
                print('Main UI passed: admin delists own/others, user delists own only in detail/home, support permissions, guest hidden, cancel, existing APIs and four viewport widths.')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    run()
