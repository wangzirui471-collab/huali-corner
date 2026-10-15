"""End-to-end browser run; uses isolated server data and real generated test photos."""
import tempfile,threading,sys,io,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import make_server
from PIL import Image
from playwright.sync_api import sync_playwright

def run():
 with tempfile.TemporaryDirectory() as tmp:
  Path('/workspace/campus-market/artifacts').mkdir(exist_ok=True)
  server=make_server(tmp,0,seed=True);threading.Thread(target=server.serve_forever,daemon=True).start()
  errors=[]
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle')
    page.get_by_text('计算机工程学院',exact=False).first.wait_for()
    assert page.locator('.product-card').count()>=6
    page.get_by_role('button',name='登录 / 注册').click()
    page.get_by_role('button',name='卖家体验').click()
    page.get_by_role('button',name='发布闲置',exact=True).first.click()
    page.locator('[name=title]').fill('浏览器测试教材')
    page.locator('[name=description]').fill('测试发布：有少量笔记，无缺页，附练习册')
    page.locator('[name=price]').fill('12')
    page.locator('[name=publisher]').fill('测试出版社')
    for angle,color in [('front','red'),('side','green'),('top','blue')]:
     f=Path(tmp)/(angle+'.png');Image.new('RGB',(180,180),color).save(f)
     page.locator('[name='+angle+']').set_input_files(str(f))
    page.get_by_role('button',name='确认发布').click()
    page.get_by_role('heading',name='浏览器测试教材',exact=True).wait_for()
    assert page.get_by_text('模拟交易',exact=False).count()>0
    page.get_by_role('button',name='加入取货清单').click()
    page.get_by_role('button',name='我的',exact=True).click()
    page.get_by_role('button',name='退出登录').click()
    page.get_by_role('button',name='登录 / 注册').click();page.get_by_role('button',name='买家体验').click()
    page.get_by_role('button',name='逛逛',exact=True).first.click()
    page.locator('.card-title').filter(has_text='浏览器测试教材').click()
    page.get_by_role('button',name='收藏',exact=True).click()
    page.get_by_role('button',name='加入取货清单').click()
    page.get_by_role('button',name='取货清单',exact=False).first.click()
    page.locator('[name=appointment]').fill(time.strftime('%Y-%m-%dT%H:%M',time.localtime(time.time()+7200)))
    page.get_by_role('button',name='生成模拟订单').click()
    page.get_by_role('button',name='模拟付款',exact=True).first.click()
    page.get_by_role('button',name='申请售后',exact=True).first.click()
    page.locator('[name=subject]').fill('测试售后')
    page.locator('[name=body]').fill('约定交付问题，申请退货反馈')
    page.get_by_role('button',name='提交工单',exact=True).click()
    
    try: page.get_by_text('测试售后',exact=True).wait_for(timeout=5000)
    except Exception:
     print('FAILURE PAGE:',page.locator('body').inner_text())
     raise
    page.get_by_role('button',name='我的',exact=True).click();page.get_by_role('button',name='退出登录').click()
    page.get_by_role('button',name='登录 / 注册').click();page.get_by_role('button',name='客服体验').click()
    page.get_by_role('button',name='客服工作台',exact=True).first.click()
    page.screenshot(path='/workspace/campus-market/artifacts/support-workbench.png',full_page=True)
    page.get_by_text('测试售后',exact=True).click()
    page.locator('[name=reason]').fill('测试：核实后双方同意退款')
    page.get_by_role('button',name='模拟退款',exact=True).click()
    page.get_by_text('已解决',exact=False).first.wait_for()
    page.get_by_role('button',name='社区',exact=True).first.click()
    page.get_by_role('button',name='加入总聊',exact=True).click()
    page.locator('[name=message]').fill('软件试点群聊测试')
    page.get_by_role('button',name='发送',exact=True).click()
    page.get_by_text('软件试点群聊测试',exact=True).wait_for()
    page.get_by_role('button',name='逛逛',exact=True).first.click()
    page.locator('#toast.show').wait_for(state='hidden')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    Path('/workspace/campus-market/artifacts').mkdir(exist_ok=True)
    page.screenshot(path='/workspace/campus-market/artifacts/mobile-home.png',full_page=True)
    page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path='/workspace/campus-market/artifacts/desktop-home.png',full_page=True)
    assert not errors,errors
    browser.close()
    print('Browser passed: upload/publish, favorite, checkout, simulated payment, dispute/refund, group chat, mobile layout; no JS errors.')
  finally:server.shutdown();server.server_close()
if __name__=='__main__':run()
