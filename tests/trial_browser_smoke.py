"""Two separate student accounts use the real persistent trial backend."""
import io
import sys
import tempfile
import threading
import time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import make_server

with tempfile.TemporaryDirectory() as root:
    server=make_server(root,0,trial=True)
    server.market.bootstrap_admin('13900000088','OperatorPassword2026!')
    threading.Thread(target=server.serve_forever,daemon=True).start()
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            seller=browser.new_page(viewport={'width':1440,'height':1000})
            buyer=browser.new_page(viewport={'width':390,'height':844})
            for page in [seller,buyer]:page.on('pageerror',lambda error:errors.append(str(error)))
            base='http://127.0.0.1:'+str(server.server_port)
            recovery={}
            for page,phone,nickname in [(seller,'13900000011','试用卖家'),(buyer,'13900000022','试用买家')]:
                page.goto(base,wait_until='networkidle')
                page.get_by_role('button',name='登录 / 注册',exact=True).click()
                expect(page.get_by_role('dialog')).to_contain_text('手机号未验证')
                expect(page.locator('[data-action=demo-login]')).to_have_count(0)
                page.get_by_role('button',name='注册账号',exact=True).click()
                page.locator('[name=phone]').fill(phone)
                page.locator('[name=nickname]').fill(nickname)
                page.locator('[name=password]').fill('StudentPassword2026!')
                page.locator('[name=password_confirm]').fill('StudentPassword2026!')
                page.locator('[name=agree]').check()
                page.get_by_role('button',name='注册并登录',exact=True).click()
                expect(page.get_by_role('heading',name='保存你的账号恢复码',exact=True)).to_be_visible()
                recovery[phone]=page.locator('#recovery-code').inner_text()
                page.get_by_role('button',name='已保存，继续使用',exact=True).click()
                expect(page.locator('.account-button')).to_contain_text(nickname)
            seller.get_by_role('button',name='发布闲置',exact=True).first.click()
            seller.locator('[name=title]').fill('学院试用二手教材')
            seller.locator('[name=description]').fill('试用测试书籍，有少量笔记，无缺页。')
            seller.locator('[name=publisher]').fill('测试出版社')
            seller.locator('[name=price]').fill('12')
            for angle,color in [('front','red'),('side','green'),('top','blue')]:
                out=io.BytesIO();Image.new('RGB',(180,180),color).save(out,'PNG')
                seller.locator('[name='+angle+']').set_input_files({'name':angle+'.png','mimeType':'image/png','buffer':out.getvalue()})
            seller.get_by_role('button',name='确认发布',exact=True).click()
            expect(seller.get_by_role('heading',name='学院试用二手教材',exact=True)).to_be_visible()
            product_url=seller.url
            buyer.goto(product_url,wait_until='networkidle')
            buyer.get_by_role('button',name='收藏',exact=True).click()
            buyer.get_by_role('button',name='加入取货清单',exact=True).click()
            buyer.get_by_role('button',name='取货清单',exact=False).first.click()
            buyer.locator('[name=appointment]').fill(time.strftime('%Y-%m-%dT%H:%M',time.localtime(time.time()+7200)))
            buyer.get_by_role('button',name='生成模拟订单',exact=True).click()
            buyer.get_by_role('button',name='模拟付款',exact=True).first.click()
            expect(buyer.locator('.order-card').first).to_contain_text('待交付')
            token=buyer.evaluate("sessionStorage.getItem('hc-token')")
            response=buyer.request.get(base+'/api/admin',headers={'Authorization':'Bearer '+token})
            assert response.status==403
            seller.goto(base+'/#orders',wait_until='networkidle')
            expect(seller.locator('.order-card').first).to_contain_text('学院试用二手教材')
            buyer.goto(base+'/#me',wait_until='networkidle')
            buyer.get_by_role('button',name='修改密码',exact=True).click()
            buyer.locator('[name=old_password]').fill('StudentPassword2026!')
            buyer.locator('[name=new_password]').fill('ChangedPassword2026!')
            buyer.locator('[name=password_confirm]').fill('ChangedPassword2026!')
            buyer.get_by_role('button',name='确认修改密码',exact=True).click()
            expect(buyer.get_by_role('heading',name='保存你的账号恢复码',exact=True)).to_be_visible()
            buyer.get_by_role('button',name='已保存，继续使用',exact=True).click()
            buyer.get_by_role('button',name='登录 / 注册',exact=True).click()
            buyer.locator('[name=phone]').fill('13900000022')
            buyer.locator('[name=password]').fill('ChangedPassword2026!')
            buyer.get_by_role('button',name='登录',exact=True).click()
            expect(buyer.locator('.account-button')).to_contain_text('试用买家')
            buyer.goto(base+'/#me',wait_until='networkidle')
            buyer.get_by_role('button',name='退出登录',exact=True).click()
            buyer.get_by_role('button',name='登录 / 注册',exact=True).click()
            buyer.get_by_role('button',name='使用恢复码找回',exact=True).click()
            buyer.locator('[name=phone]').fill('13900000011')
            buyer.locator('[name=recovery_code]').fill(recovery['13900000011'])
            buyer.locator('[name=new_password]').fill('RecoveredPassword2026!')
            buyer.locator('[name=password_confirm]').fill('RecoveredPassword2026!')
            buyer.get_by_role('button',name='重置密码',exact=True).click()
            expect(buyer.get_by_role('heading',name='保存你的账号恢复码',exact=True)).to_be_visible()
            seller.reload(wait_until='networkidle')
            expect(seller.locator('.account-button')).to_contain_text('登录 / 注册')
            assert not errors,errors
            buyer.screenshot(path='/tmp/huali-trial-recovery.png',full_page=True)
            browser.close()
        print('Trial browser passed: separate student registration, publishing, favorite, order/payment, permissions, password change, recovery and session revocation.')
    finally:server.shutdown();server.server_close()
