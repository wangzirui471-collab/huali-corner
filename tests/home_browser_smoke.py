"""Homepage UI regression; isolated temporary database, never production data."""
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend mission'))
from server import make_server


def run():
    output = Path(os.environ.get('HOME_SCREENSHOTS', tempfile.mkdtemp(prefix='home-ui-')))
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as data:
        server = make_server(data, 0, trial=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        market = server.market
        seller = market.register_password('13900009871', 'HomepageSeller2026!', '林同学')
        buyer = market.register_password('13900009872', 'HomepageBuyer2026!', '陈同学')
        admin = market.bootstrap_admin('13900009873', 'HomepageAdmin2026!')
        administrator = market.login_password('13900009873', 'HomepageAdmin2026!')
        uid = seller['user']['id']
        photos = []
        for angle, color in [('front', '#b9c3b1'), ('side', '#cbbca2'), ('top', '#a9bbc3')]:
            image = io.BytesIO()
            Image.new('RGB', (320, 320), color).save(image, 'PNG')
            photos.append(market.add_upload(uid, image.getvalue(), angle)['id'])
        first = market.publish(uid, dict(title='数据结构教材 01', category='books', price=1200,
            original_price=3800, delivery_fee=200, delivery='both', region='图书馆 · 正门',
            description='正版教材，少量笔记，无缺页。', photos=photos, edition='第二版',
            publisher='高等教育出版社', notes='少量笔记', missing='无缺页', accessories='无附件'))['id']
        with market.tx() as connection:
            row = dict(connection.execute('SELECT * FROM products WHERE id=?', (first,)).fetchone())
            keys = list(row)
            for i in range(1, 53):
                clone = {**row, 'id': first+i, 'title': f'数据结构教材 {i+1:02}', 'price': 0 if i==10 else 1000+i*100}
                connection.execute('INSERT INTO products('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')', tuple(clone[k] for k in keys))
        base = f'http://127.0.0.1:{server.server_port}'
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('CHROME_PATH', r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
                page = browser.new_page(viewport={'width':1440,'height':1100}, reduced_motion='reduce')
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.add_init_script('sessionStorage.setItem("hc-token",'+json.dumps(buyer['token'])+');')
                page.goto(base+'/#home', wait_until='networkidle')
                expect(page.locator('.product-card')).to_have_count(24)
                expect(page.locator('.home-slide:visible')).to_have_count(1)
                assert page.locator('.home-banner').bounding_box()['y'] < page.locator('.home-channels').bounding_box()['y'] < page.locator('.home-shortcuts').bounding_box()['y']
                expect(page.locator('.home-shortcuts button')).to_have_count(9)
                expect(page.locator('.product-card [data-action="delist"],.product-card [data-action="moderate-product"]')).to_have_count(0)
                for route in ['home','community','forum','me']:
                    expect(page.locator('.desktop-navigation [data-go="'+route+'"]').first).to_be_visible()
                expect(page.locator('.header-publish')).to_be_visible()
                page.screenshot(path=str(output/'home-desktop.png'), full_page=False)
                page.get_by_role('button', name='下一张', exact=True).click()
                expect(page.locator('.home-slide-campus')).to_be_visible()
                expect(page.locator('[data-action="home-pause"]')).to_have_text('自动播放')
                page.get_by_role('button', name='上一张', exact=True).click()

                failed = {'done':False,'calls':0}
                def product_route(route):
                    query=parse_qs(urlsplit(route.request.url).query)
                    if query.get('page')==['2']:
                        failed['calls']+=1
                        if not failed['done']:
                            failed['done']=True
                            route.fulfill(status=503, content_type='application/json', body='{"error":"test outage"}')
                            return
                    route.continue_()
                page.route('**/api/products?*', product_route)
                page.locator('[data-action="load-more"]').scroll_into_view_if_needed()
                expect(page.locator('[data-action="load-more"]')).to_have_text('重新加载')
                expect(page.locator('.product-card')).to_have_count(24)
                assert failed['calls']==1
                page.locator('[data-action="load-more"]').click()
                expect(page.locator('.product-card')).to_have_count(48)
                assert failed['calls']==2
                page.locator('[data-action="load-more"]').scroll_into_view_if_needed()
                expect(page.locator('.product-card')).to_have_count(53)
                assert len(set(page.locator('.product-card').evaluate_all('(items)=>items.map(x=>x.dataset.productId)')))==53
                expect(page.locator('[data-action="load-more"]')).to_be_hidden()
                favorite=page.locator('.favorite-button').last
                favorite.click()
                expect(favorite).to_have_attribute('aria-pressed','true')
                expect(page.locator('.product-card')).to_have_count(53)
                assert page.evaluate('window.scrollY')>600
                favorite.click()
                expect(favorite).to_have_attribute('aria-pressed','false')
                page.locator('[data-action="home-top"]').click()
                page.wait_for_function('window.scrollY===0')
                page.locator('#search-form input').fill('没有这个关键词')
                page.locator('#search-form').get_by_role('button', name='搜索', exact=True).click()
                expect(page.get_by_role('heading',name='暂时没有匹配的商品')).to_be_visible()
                page.locator('.home-channels [data-value="books"]').click()
                expect(page.locator('.product-card')).to_have_count(24)
                page.locator('[data-action="free-shelf"]').click()
                expect(page.locator('.product-card')).to_have_count(1)
                expect(page.locator('.home-feed h2')).to_contain_text('免费好物')

                # A delayed old request must not replace a newer route.
                pending=[]
                def hold(route): pending.append(route)
                page.unroute('**/api/products?*', product_route)
                page.route('**/api/products?*', hold)
                page.locator('.home-channels [data-value=""]').click()
                page.wait_for_function('document.querySelector(".home-page")!==null')
                page.locator('.desktop-navigation [data-go="community"]').click()
                expect(page).to_have_url(base+'/#community')
                expect(page.locator('.community-layout')).to_be_visible()
                assert pending
                for route in pending: route.fulfill(status=200, content_type='application/json', body='[]')
                page.unroute('**/api/products?*', hold)
                expect(page.locator('.community-layout')).to_be_visible()
                expect(page.locator('.home-banner')).to_have_count(0)

                for width in [390,320,768]:
                    page.set_viewport_size({'width':width,'height':900})
                    page.goto(base+'/#home',wait_until='networkidle')
                    expect(page.locator('.home-banner')).to_be_visible()
                    expect(page.locator('.header-actions .cart-button .icon')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'overflow {width}'
                    expect(page.locator('.mobile-nav [data-go="forum"]')).to_be_visible()
                    expect(page.locator('.mobile-publish')).to_be_visible()
                    page.screenshot(path=str(output/f'home-mobile-{width}.png'))
                page.set_viewport_size({'width':1440,'height':1100})
                page.goto(base+'/#favorites',wait_until='networkidle')
                expect(page.get_by_role('heading',name='我的收藏',exact=True)).to_be_visible()
                expect(page.locator('.home-banner')).to_have_count(0)
                page.goto(base+'/#publish',wait_until='networkidle')
                expect(page.locator('#publish-form')).to_be_visible()
                page.goto(base+'/#forum',wait_until='networkidle')
                expect(page.locator('.forum-surface')).to_be_visible()
                page.goto(base+'/#messages',wait_until='networkidle')
                expect(page.locator('.wx-chat')).to_be_visible()

                # Owners retain delist/relist in My Listings; staff workbench remains.
                own=browser.new_page(viewport={'width':1440,'height':1100})
                own.on('pageerror', lambda error: errors.append(str(error)))
                own.add_init_script('sessionStorage.setItem("hc-token",'+json.dumps(seller['token'])+');')
                own.goto(base+'/#listings',wait_until='networkidle')
                own.on('dialog',lambda dialog:dialog.accept())
                own.locator('[data-action="delist"]').first.click()
                expect(own.locator('[data-action="relist"]')).to_have_count(1)
                own.locator('[data-action="relist"]').click()
                expect(own.locator('[data-action="delist"]')).to_have_count(53)
                staff=browser.new_page(viewport={'width':1440,'height':1100})
                staff.add_init_script('sessionStorage.setItem("hc-token",'+json.dumps(administrator['token'])+');')
                staff.goto(base+'/#staff/products',wait_until='networkidle')
                expect(staff.locator('[data-action="moderate-product"]').first).to_be_attached()
                # Progressive enhancement: manual loading works without an observer.
                fallback=browser.new_page(viewport={'width':1440,'height':1100})
                fallback.add_init_script('delete window.IntersectionObserver;')
                fallback.clock.install()
                fallback.goto(base+'/#home',wait_until='networkidle')
                expect(fallback.locator('.product-card')).to_have_count(24)
                fallback.locator('.home-banner').hover()
                fallback.clock.fast_forward(8000)
                expect(fallback.locator('.home-slide-books')).to_be_visible()
                fallback.locator('.brand').hover()
                fallback.clock.fast_forward(7100)
                expect(fallback.locator('.home-slide-campus')).to_be_visible()
                fallback.locator('[data-action="home-pause"]').focus()
                fallback.clock.fast_forward(8000)
                expect(fallback.locator('.home-slide-campus')).to_be_visible()
                fallback.locator('[data-action="load-more"]').click()
                expect(fallback.locator('.product-card')).to_have_count(48)
                assert not errors, errors
                browser.close()
                print('PASS: layout, carousel, pagination/retry/dedup, favorite position, search, free, stale response, 3 mobile widths, publish/forum/messages, owner delist/relist and staff controls')
                print('Screenshots: '+str(output))
        finally:
            server.shutdown()
            server.server_close()


if __name__=='__main__': run()
