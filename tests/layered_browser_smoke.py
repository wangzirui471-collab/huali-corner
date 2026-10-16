"""Real Chromium journeys across layered UI, drafts, catalog and independent staff."""
import io
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import make_server
from PIL import Image
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=8000)


def run():
 with tempfile.TemporaryDirectory() as root:
  server=make_server(root,0,trial=True)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  m=server.market
  m.bootstrap_admin('13900000700','OperatorPassword2026!')
  admin=m.login_password('13900000700','OperatorPassword2026!')
  seller=m.register_password('13900000701','SellerPassword2026!','卖家同学')
  buyer=m.register_password('13900000702','BuyerPassword2026!','买家同学')
  m.create_support(admin['user']['id'],dict(phone='13900000703',password='WorkerPassword2026!',nickname='客服甲'))
  worker=m.login_password('13900000703','WorkerPassword2026!')
  base='http://127.0.0.1:'+str(server.server_port);errors=[];failed=[];checks=[]
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    def page_for(session):
     page=browser.new_page(viewport={'width':390,'height':844})
     page.on('pageerror',lambda e:errors.append(str(e)))
     page.on('response',lambda r:failed.append((r.status,r.url)) if r.status>=400 else None)
     page.goto(base,wait_until='networkidle')
     page.evaluate('(token)=>sessionStorage.setItem("hc-token",token)',session['token'])
     page.reload(wait_until='networkidle');return page
    page=page_for(seller)
    page.goto(base+'/#publish/new');expect(page.locator('#publish-form')).to_be_visible()
    page.locator('[name=title]').fill('可续编的数据结构');page.locator('[name=price]').fill('12.50')
    for angle,color in [('front','red'),('side','green'),('top','blue')]:
     data=io.BytesIO();Image.new('RGB',(80,80),color).save(data,'PNG')
     page.locator(f'[name={angle}]').set_input_files(dict(name=angle+'.png',mimeType='image/png',buffer=data.getvalue()))
    expect(page.locator('[data-testid=draft-status]')).to_contain_text('已保存',timeout=10000)
    page.locator('[data-draft-save]').click()
    page.goto(base+'/#drafts');expect(page.locator('.draft-list')).to_contain_text('可续编的数据结构')
    page.get_by_role('button',name='继续编辑').click()
    expect(page.locator('.photo-count')).to_contain_text('3 张')
    page.locator('.publish-submit button').click();expect(page.locator('.detail-grid')).to_be_visible()
    pid=int(page.url.split('/')[-1]);assert m.product(pid)['price']==1250;checks.append('三步发布、三图上传、草稿恢复')
    page.goto(base+'/#edit/'+str(pid));expect(page.locator('[name=price]')).to_have_value('12.50')
    page.locator('[name=price]').fill('18.25')
    page.locator('.publish-submit button').click();expect(page.locator('.detail-grid')).to_be_visible()
    assert m.product(pid)['price']==1825;checks.append('原地编辑并保留三张实拍')
    page.goto(base+'/#listings');expect(page.get_by_role('button',name='编辑',exact=True)).to_be_visible()
    page.on('dialog',lambda d:d.accept())
    page.get_by_role('button',name='下架',exact=True).click();expect(page.get_by_role('button',name='恢复上架',exact=True)).to_be_visible()
    page.get_by_role('button',name='恢复上架',exact=True).click();expect(page.get_by_role('button',name='下架',exact=True)).to_be_visible();checks.append('主动下架与恢复')
    page.goto(base+'/#home');page.locator('[data-action=open-filter]').click()
    page.locator('#catalog-filter-form [name=category]').select_option('books')
    page.locator('#catalog-filter-form [name=min_price]').fill('18')
    page.locator('#catalog-filter-form [name=max_price]').fill('19')
    page.locator('#catalog-filter-form button[type=submit]').click() if page.locator('#catalog-filter-form button[type=submit]').count() else page.get_by_role('button',name='应用筛选',exact=True).click()
    expect(page.locator('.product-card')).to_have_count(1);checks.append('组合筛选与金额换算')
    order=m.checkout(buyer['user']['id'],dict(product_ids=[pid],delivery='pickup',appointment=time.time()+7200,key='layered-browser'))
    page.goto(base+'/#messages');expect(page.locator('[data-notification-center]')).to_contain_text('有新订单')
    checks.append('卖家收到订单通知')
    m.order_action(buyer['user']['id'],order['id'],'pay',{})
    m.order_action(seller['user']['id'],order['id'],'deliver',{})
    case=m.create_ticket(buyer['user']['id'],dict(type='refund',order_id=order['id'],subject='退货协商',body='发现描述问题',refund_mode='return_refund'))
    work=page_for(worker);work.goto(base+'/#staff');expect(work.locator('.ticket-list')).to_contain_text('退货协商')
    work.locator('.ticket-row').click();expect(work.get_by_role('button',name='提交退款建议')).to_be_visible()
    assert not work.get_by_role('button',name='模拟退款',exact=True).count()
    work.locator('[name=reason]').fill('已核对双方材料，建议退货退款')
    work.get_by_role('button',name='提交退款建议').click();expect(work.locator('h1')).to_contain_text('退货协商')
    assert m.ticket(admin['user']['id'],case['id'])['requested_amount']==1825;checks.append('客服工作台与分权退款建议')
    m.return_action(buyer['user']['id'],case['id'],'return_sent');m.return_action(seller['user']['id'],case['id'],'confirm_return')
    manager=page_for(admin);manager.goto(base+'/#ticket/'+str(case['id']))
    manager.locator('[name=reason]').fill('双方已确认实物退回，批准模拟退款')
    manager.get_by_role('button',name='模拟退款',exact=True).click();expect(manager.locator('.tag').first).to_contain_text('已解决')
    page.goto(base+'/#listings');expect(page.get_by_role('button',name='重新上架',exact=True)).to_be_visible()
    page.get_by_role('button',name='重新上架',exact=True).click();expect(page.locator('#publish-form')).to_contain_text('退回物品')
    page.locator('.publish-submit button').click();expect(page.locator('.detail-grid')).to_be_visible();checks.append('退货确认、管理员退款与实物重售')
    page.goto(base+'/#home')
    for width in [375,390,768,1440]:
     page.set_viewport_size({'width':width,'height':900})
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    checks.append('四档屏宽无整页横向溢出')
    assert not errors,errors
    assert not failed,failed
    print('Layered Chromium journeys passed:',len(checks),'; '.join(checks))
    browser.close()
  finally:server.shutdown();server.server_close()

if __name__=='__main__':run()
