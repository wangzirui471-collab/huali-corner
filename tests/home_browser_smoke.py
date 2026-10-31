"""Homepage UI regression; isolated temporary database, never production data.

首页改版后的契约：
  · 主视觉只有一条轮播，Element Plus 岛负责渲染；岛不可用时退回原生轮播，两套外观一致。
  · 频道只有一排（5 个分类 + 免费送 + 校园求购），原来的第二排快捷宫格进「筛选」弹窗。
  · 商品流、分页、收藏、排序、筛选、推荐轨、回到顶部全部留在原生层。
"""
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

                # Element Plus 岛挂载后：一条轮播、六张专题、一排频道，原生兜底不再存在。
                expect(page.locator('.home-chrome .hc-root')).to_be_visible()
                expect(page.locator('.home-chrome .el-carousel__item')).to_have_count(6)
                expect(page.locator('.home-chrome .hc-slide')).to_have_count(6)
                # 每张专题自带配色档位；岛必须沿用兜底同一套 tone class。
                expect(page.locator('.home-chrome .hc-slide[class*="hc-tone-"]')).to_have_count(6)
                expect(page.locator('[data-home-carousel]')).to_have_count(0)
                expect(page.locator('.hc-cats .hc-cat')).to_have_count(7)
                expect(page.locator('.hc-cat.active')).to_have_count(1)
                expect(page.locator('.hc-cat.active')).to_contain_text('为你推荐')
                # 去重：分类入口全站只有这一排，原来的第二排快捷宫格必须消失。
                expect(page.locator('.home-page [data-action="market-channel"]')).to_have_count(5)
                expect(page.locator('.home-page .category-grid, .home-page .home-shortcuts')).to_have_count(0)
                expect(page.locator('.home-page [data-action="free-shelf"]')).to_have_count(3)  # 频道 + 免费送专题 + 收尾召唤
                assert page.locator('.home-chrome').bounding_box()['y'] < page.locator('.rec-rail').bounding_box()['y'] < page.locator('.home-feed').bounding_box()['y'] < page.locator('.home-cta').bounding_box()['y']
                expect(page.locator('.product-card [data-action="delist"],.product-card [data-action="moderate-product"]')).to_have_count(0)
                for route in ['home','community','forum','me','publish']:
                    expect(page.locator('.desktop-navigation [data-go="'+route+'"]').first).to_be_visible()
                page.screenshot(path=str(output/'home-desktop.png'), full_page=False)

                # 主视觉每张都真的能去该去的地方（岛内按钮走原生事件层）。
                # el-carousel 用 transform 平移，非当前页依然「可见」，只能按 is-active 取。
                expect(page.locator('.el-carousel__item.is-active .hc-slide')).to_have_count(1)
                page.locator('.el-carousel__item.is-active .hc-slide').click()
                expect(page.locator('.hc-cat.active')).to_contain_text('教材书籍')
                page.locator('.hc-cat[data-value=""]').click()
                expect(page.locator('.hc-cat.active')).to_contain_text('为你推荐')

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
                page.locator('.hc-cat[data-value="books"]').click()
                expect(page.locator('.product-card')).to_have_count(24)
                # 关键词快捷搬进筛选弹窗，功能不减入口。
                page.locator('[data-action="open-filter"]').click()
                expect(page.locator('.filter-shortcuts button')).to_have_count(6)
                page.locator('.filter-shortcuts button', has_text='台灯照明').click()
                expect(page.locator('#overlay')).to_be_empty()
                expect(page.locator('.home-feed h2')).to_contain_text('搜索结果')
                expect(page.locator('.home-feed-context')).to_contain_text('搜索：灯')
                page.locator('[data-action="free-shelf"]').first.click()
                expect(page.locator('.product-card')).to_have_count(1)
                expect(page.locator('.home-feed h2')).to_contain_text('免费好物')
                expect(page.locator('.hc-cat.active')).to_contain_text('免费送')

                # A delayed old request must not replace a newer route.
                pending=[]
                def hold(route): pending.append(route)
                page.unroute('**/api/products?*', product_route)
                page.route('**/api/products?*', hold)
                page.locator('.hc-cat[data-value=""]').click()
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
                expect(page.locator('.home-chrome')).to_have_count(0)

                for width in [390,320,768]:
                    page.set_viewport_size({'width':width,'height':900})
                    page.goto(base+'/#home',wait_until='networkidle')
                    expect(page.locator('.home-chrome')).to_be_visible()
                    expect(page.locator('.home-chrome .hc-slide')).to_have_count(6)
                    expect(page.locator('.header-actions .cart-button .icon')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'overflow {width}'
                    expect(page.locator('.mobile-nav [data-go="forum"]')).to_be_visible()
                    expect(page.locator('.mobile-publish')).to_be_visible()
                    expect(page.locator('.mobile-nav > button')).to_have_count(5)
                    expect(page.locator('.mobile-nav [data-go="me"]')).to_have_count(0)
                    nav=page.locator('.mobile-publish').bounding_box()
                    assert abs(nav['x']+nav['width']/2-width/2)<=1
                    expect(page.locator('.account-button[data-go="me"]')).to_be_visible()
                    page.screenshot(path=str(output/f'home-mobile-{width}.png'))
                page.set_viewport_size({'width':1440,'height':1100})
                page.goto(base+'/#favorites',wait_until='networkidle')
                expect(page.get_by_role('heading',name='我的收藏',exact=True)).to_be_visible()
                expect(page.locator('.home-chrome')).to_have_count(0)
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

                # 岛取不到时的兜底轮播：仍然是「一条轮播 + 六个专题」，定时器与圆点照常工作。
                fallback=browser.new_page(viewport={'width':1440,'height':1100})
                fallback.add_init_script('window.HC_HOME_ISLAND=false;delete window.IntersectionObserver;')
                fallback.on('pageerror', lambda error: errors.append(str(error)))
                fallback.clock.install()
                fallback.goto(base+'/#home',wait_until='networkidle')
                expect(fallback.locator('.product-card')).to_have_count(24)
                expect(fallback.locator('.home-chrome .hc-root')).to_have_count(0)
                hero=fallback.locator('[data-home-carousel="hero"]')
                expect(hero).to_be_visible()
                expect(hero.locator('[data-promo-slide]')).to_have_count(6)
                def active(index):
                    expect(hero.locator('[data-promo-slide="'+str(index)+'"]')).to_be_visible()
                    expect(hero.locator('[data-promo-slide]:visible')).to_have_count(1)
                active(0)
                fallback.clock.fast_forward(7100); active(1)
                fallback.clock.fast_forward(7100); active(2)
                fallback.clock.fast_forward(7100); active(3)
                # 圆点直接选页，定时器继续走（旧版就没有暂停键）。
                hero.locator('[data-action="home-slide"][data-index="0"]').click(); active(0)
                fallback.clock.fast_forward(7100); active(1)
                fallback.screenshot(path=str(output/'home-fallback-hero.png'))
                # 手动加载在没有 IntersectionObserver 时仍然可用。
                expect(fallback.locator('[data-action="load-more"]')).to_be_visible()
                fallback.locator('[data-action="load-more"]').click()
                expect(fallback.locator('.product-card')).to_have_count(48)
                # 六张专题逐张点开：三个分类、一个免费送、社区、发布（未登录弹登录框）。
                for index, label in [(0,'教材书籍'),(1,'宿舍生活'),(2,'运动好物')]:
                    hero.locator('[data-action="home-slide"][data-index="'+str(index)+'"]').click()
                    hero.locator('.hc-slide:visible').click()
                    expect(fallback.locator('.hc-cat.active')).to_contain_text(label)
                    fallback.locator('.hc-cat[data-value=""]').click()
                    hero=fallback.locator('[data-home-carousel="hero"]')
                hero.locator('[data-action="home-slide"][data-index="4"]').click()
                hero.locator('.hc-slide:visible').click()
                expect(fallback.locator('.home-feed h2')).to_contain_text('免费好物')
                fallback.goto(base+'/#home',wait_until='networkidle')
                hero=fallback.locator('[data-home-carousel="hero"]')
                hero.locator('[data-action="home-slide"][data-index="3"]').click()
                hero.locator('.hc-slide:visible').click()
                expect(fallback.locator('.community-hub')).to_be_visible()
                fallback.locator('.brand').click()
                hero=fallback.locator('[data-home-carousel="hero"]')
                hero.locator('[data-action="home-slide"][data-index="5"]').click()
                hero.locator('.hc-slide:visible').click()
                expect(fallback.locator('[data-public-demo-feature]')).to_have_count(0)
                # Guest publish correctly opens the existing login guard.
                expect(fallback.get_by_role('dialog')).to_be_visible()
                assert not errors, errors
                browser.close()
                print('PASS: Element Plus hero island + native fallback, one channel row, six destinations, paging/favorites, filter shortcuts, stale isolation, three mobile widths, centered five-slot nav, upper My Account, retained community hub and owner/staff functions')
                print('Screenshots: '+str(output))
        finally:
            server.shutdown()
            server.server_close()


if __name__=='__main__': run()
