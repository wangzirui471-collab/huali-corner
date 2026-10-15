"""Marketplace visual hierarchy, responsive behavior and preserved interactions."""
import tempfile,threading,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import make_server
from playwright.sync_api import sync_playwright,expect

with tempfile.TemporaryDirectory() as root:
 server=make_server(root,0,seed=True);threading.Thread(target=server.serve_forever,daemon=True).start()
 errors=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':390,'height':844})
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
   header=page.locator('[data-market-header]')
   assert header.count()==1,'Marketplace needs a top search header instead of the old sidebar/hero layout'
   assert page.get_by_role('searchbox',name='搜索商品').is_visible()
   assert page.get_by_role('searchbox',name='搜索商品').bounding_box()['y']<140
   assert page.locator('.product-card').first.bounding_box()['y']<600,'Real product feed should start within the first screen'
   page.get_by_role('button',name='二手书',exact=True).first.click()
   expect(page.locator('.product-card')).to_have_count(6)
   page.get_by_role('searchbox',name='搜索商品').fill('Python')
   page.locator('#search-form').get_by_role('button',name='搜索',exact=True).click()
   expect(page.locator('.product-card')).to_have_count(1)
   assert 'Python' in page.locator('.card-title').inner_text()
   page.locator('.card-title').click()
   page.get_by_role('button',name='加入取货清单',exact=True).wait_for()
   assert page.locator('#main-photo').count()==1
   page.get_by_role('button',name='返回逛逛',exact=False).click()
   page.get_by_role('searchbox',name='搜索商品').fill('')
   page.locator('#search-form').get_by_role('button',name='搜索',exact=True).click()
   page.get_by_role('button',name='推荐',exact=True).click()
   expect(page.locator('.product-card')).to_have_count(9)
   artifacts=Path('/workspace/campus-market/artifacts');artifacts.mkdir(exist_ok=True)
   for width,height,label in [(375,812,'small-mobile'),(390,844,'mobile'),(768,1024,'tablet'),(1440,1000,'desktop')]:
    page.set_viewport_size({'width':width,'height':height})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),label+' overflows horizontally'
    assert page.get_by_role('searchbox',name='搜索商品').is_visible()
    page.screenshot(path=str(artifacts/f'redesign-{label}.png'),full_page=label in ['mobile','desktop'])
   assert not errors,errors
   browser.close()
   print('Redesign checks passed: prominent search, category filtering, product detail, product-first fold, 375/390/768/1440 layouts.')
 finally:server.shutdown();server.server_close()
