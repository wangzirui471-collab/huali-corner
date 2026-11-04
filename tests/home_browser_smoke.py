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
                # 主轮播使用真实 Element Plus，旁边两个快捷入口保持可见。
                expect(page.locator('.mint-carousel .el-carousel__item')).to_have_count(4)
                expect(page.locator('.mint-carousel .el-carousel__item.is-active')).to_have_count(1)
                expect(page.locator('.mint-side button')).to_have_count(2)
                # 检查照片真正加载，避免 CSS 或资源返回空白却通过 DOM 数量断言。
                page.wait_for_function("Array.from(document.querySelectorAll('.mint-cover')).length === 6 && Array.from(document.querySelectorAll('.mint-cover')).every(image => image.complete && image.naturalWidth > 0)")
                side_photos = page.locator('.mint-side .mint-cover').evaluate_all('(images)=>images.map(image=>image.getAttribute("src"))')
                assert all('/market-' in photo for photo in side_photos), side_photos
                expect(page.get_by_role('button', name='播放轮播', exact=True)).to_have_count(0)
                expect(page.get_by_role('button', name='暂停轮播', exact=True)).to_have_count(0)
                # 参考图的版面顺序：主视觉 → 频道条 → 转角发现（商品流）。
                assert page.locator('.home-hero').bounding_box()['y'] < page.locator('.home-channels').bounding_box()['y'] < page.locator('.home-feed').bounding_box()['y']
                # 九格快捷宫格整行删掉：其中六个和频道行、顶栏跳同一页。
                expect(page.locator('.home-shortcuts')).to_have_count(0)
                expect(page.locator('.home-channel')).to_have_count(7)
                # 「小转推荐」整条轨下线。
                expect(page.locator('.rec-rail')).to_have_count(0)
                # 轮播里的宿舍、教材、求购、发布全部保留真实路由。
                expect(page.locator('.mint-carousel .mint-topic-link')).to_have_count(4)
                targets = page.locator('.mint-carousel .mint-topic-link').evaluate_all('(items)=>items.map(item=>item.dataset.go)')
                assert set(targets) == {'home/living','home/books','forum/wants','publish'}, targets
                # 频道行：六个商品频道各自带地址段，校园求购去论坛求购页。
                channel_targets = page.evaluate("""()=>[...document.querySelectorAll('.home-page .home-channel')]
                    .map(el=>el.dataset.go || ('home/'+(el.dataset.value||'')))""")
                assert len(set(channel_targets))==7, channel_targets
                expect(page.locator('.home-channel[data-go="forum/wants"]')).to_have_count(1)
                expect(page.locator('.product-card [data-action="delist"],.product-card [data-action="moderate-product"]')).to_have_count(0)
                for route in ['home','community','forum','me','publish']:
                    expect(page.locator('.desktop-navigation [data-go="'+route+'"]').first).to_be_visible()
                page.screenshot(path=str(output/'home-desktop.png'), full_page=False)

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
                page.locator('.home-channel[data-value="books"]').click()
                expect(page).to_have_url(base+'/#home/books')
                expect(page.locator('.product-card')).to_have_count(24)
                expect(page.locator('.home-feed h2')).to_contain_text('教材书籍')
                # 从筛选弹窗改用价格排序，免费教材应排在最前面。
                page.locator('[data-action="open-filter"]').click()
                page.locator('#filter-form [name=sort]').select_option('price')
                page.locator('#filter-form').get_by_role('button', name='应用筛选').click()
                expect(page.locator('#filter-form')).to_have_count(0)
                expect(page.locator('.product-card').first.locator('.browse-free-price')).to_have_text('免费送')
                page.locator('.home-channel[data-value="free"]').click()
                expect(page).to_have_url(base+'/#home/free')
                expect(page.locator('.product-card')).to_have_count(1)
                expect(page.locator('.home-feed h2')).to_contain_text('免费好物')
                expect(page.locator('.product-card .browse-free-price')).to_have_text('免费送')
                expect(page.locator('.product-card .price-line s')).to_have_count(0)
                expect(page.locator('.product-card .card-tags')).to_contain_text('自提/送货')
                expect(page.locator('.home-channel[data-value="free"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('.home-channel[data-value="books"]')).to_have_attribute('aria-pressed','false')

                # A delayed old request must not replace a newer route.
                pending=[]
                def hold(route): pending.append(route)
                page.unroute('**/api/products?*', product_route)
                page.route('**/api/products?*', hold)
                page.locator('.home-channel[data-value=""]').click()
                page.wait_for_function('document.querySelector(".home-page")!==null')
                page.locator('.desktop-navigation [data-go="community"]').click()
                expect(page).to_have_url(base+'/#community')
                expect(page.locator('.community-hub')).to_be_visible()
                expect(page.locator('.community-hub a[href="#forum/wants"]').first).to_be_visible()
                expect(page.locator('.want-board')).to_have_count(0)
                assert pending
                for route in pending: route.fulfill(status=200, content_type='application/json', body='[]')
                page.unroute('**/api/products?*', hold)
                expect(page.locator('.community-hub')).to_be_visible()
                expect(page.locator('.home-hero')).to_have_count(0)

                for width in [390,320,768]:
                    page.set_viewport_size({'width':width,'height':900})
                    page.goto(base+'/#home',wait_until='networkidle')
                    expect(page.locator('.home-hero')).to_be_visible()
                    expect(page.locator('.header-actions .cart-button .icon')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'overflow {width}'
                    expect(page.locator('.mobile-nav [data-go="forum"]')).to_be_visible()
                    expect(page.locator('.mobile-publish')).to_be_visible()
                    expect(page.locator('.mobile-nav > button')).to_have_count(5)
                    expect(page.locator('.mobile-nav [data-go="me"]')).to_have_count(0)
                    nav=page.locator('.mobile-publish').bounding_box()
                    assert abs(nav['x']+nav['width']/2-width/2)<=1
                    expect(page.locator('.account-button[data-go="me"]')).to_be_visible()
                    # 小屏从原小转入口打开真实桌宠面板，测试不调用外部模型。
                    assistant=page.get_by_role('button',name='问问小转AI')
                    expect(assistant).to_be_visible()
                    if width==320:
                        assistant.click()
                        expect(page.locator('#ai-pet-panel')).to_be_visible()
                        expect(page.locator('#ai-pet-q')).to_be_visible()
                        page.locator('#ai-pet-close').click()
                        expect(page.locator('#ai-pet-panel')).to_be_hidden()
                    page.screenshot(path=str(output/f'home-mobile-{width}.png'))
                page.set_viewport_size({'width':1440,'height':1100})
                page.goto(base+'/#favorites',wait_until='networkidle')
                expect(page.get_by_role('heading',name='我的收藏',exact=True)).to_be_visible()
                expect(page.locator('.home-hero')).to_have_count(0)
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
                carousel = fallback.locator('.mint-carousel')
                active = carousel.locator('.el-carousel__item.is-active .mint-topic-link')
                expect(active).to_have_attribute('data-go','publish')
                fallback.clock.fast_forward(8100)
                expect(active).to_have_attribute('data-go','publish')
                # 手动箭头和指示器都切换专题，减少动态效果时仍能手动切换。
                carousel.locator('.el-carousel__arrow--right').click()
                expect(active).to_have_attribute('data-go','home/books')
                fallback.emulate_media(reduced_motion='reduce')
                carousel.locator('.el-carousel__indicator').nth(3).click()
                expect(active).to_have_attribute('data-go','forum/wants')
                expect(fallback.get_by_role('button', name='播放轮播', exact=True)).to_have_count(0)
                carousel.locator('.el-carousel__indicator').nth(1).click()
                expect(active).to_have_attribute('data-go','home/books')
                active.click()
                expect(fallback).to_have_url(base+'/#home/books')
                expect(fallback.locator('.home-feed h2')).to_contain_text('教材书籍')
                fallback.locator('.mint-side [data-go="home/free"]').click()
                expect(fallback).to_have_url(base+'/#home/free')
                expect(fallback.locator('.browse-free-price')).to_have_text('免费送')
                fallback.go_back()
                expect(fallback).to_have_url(base+'/#home/books')
                fallback.go_back()
                expect(fallback).to_have_url(base+'/#home')
                expect(fallback.locator('.product-card')).to_have_count(24)
                # 主轮播资源加载失败时，静态专题和快捷路由仍然可以点击。
                without_carousel=browser.new_page()
                without_carousel.route('**/assets/home-mint/carousel-market.js*', lambda route: route.abort())
                without_carousel.goto(base+'/#home',wait_until='networkidle')
                expect(without_carousel.locator('.mint-fallback-links [data-go="forum/wants"]')).to_be_visible()
                without_carousel.locator('.mint-side [data-go="home/books"]').click()
                expect(without_carousel).to_have_url(base+'/#home/books')
                without_carousel.close()
                fallback.locator('[data-action="load-more"]').click()
                expect(fallback.locator('.product-card')).to_have_count(48)
                # 首页保留一个「发布闲置」CTA（与主视觉同屏），但顶栏那个仍然拦住未登录用户。
                expect(fallback.locator('.home-cta [data-go="publish"]')).to_have_count(1)
                fallback.locator('.home-cta [data-go="publish"]').click()
                expect(fallback.locator('[data-public-demo-feature]')).to_have_count(0)
                # Guest publish correctly opens the existing login guard.
                expect(fallback.get_by_role('dialog')).to_be_visible()
                assert not errors, errors
                browser.close()
                print('PASS: Element Plus carousel and topic shortcuts, fallback links, seven channels (six product views + forum wants), no 小转推荐 rail, per-channel URLs and back navigation, paging/favorites, stale isolation, three mobile widths, centered five-slot nav, retained community hub and owner/staff functions')
                print('Screenshots: '+str(output))
        finally:
            server.shutdown()
            server.server_close()


if __name__=='__main__': run()
