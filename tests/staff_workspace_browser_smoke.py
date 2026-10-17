"""Real browser checks for staff-only product removal and daily workbench flows."""
import io
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import make_server
from PIL import Image
from playwright.sync_api import sync_playwright, expect


def run():
    with tempfile.TemporaryDirectory() as root:
        server = make_server(root, 0, trial=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        m = server.market
        admin = m.bootstrap_admin('13900009600', 'OperatorPassword2026!')
        operator = m.login_password('13900009600', 'OperatorPassword2026!')
        worker = m.create_support(admin['id'], dict(phone='13900009601', password='WorkerPassword2026!', nickname='客服小林'))
        support = m.login_password('13900009601', 'WorkerPassword2026!')
        seller = m.register_password('13900009602', 'SellerPassword2026!', '卖家同学')
        buyer = m.register_password('13900009603', 'BuyerPassword2026!', '买家同学')
        def listing(title):
            photos = []
            for angle, color in [('front','red'), ('side','green'), ('top','blue')]:
                content = io.BytesIO(); Image.new('RGB',(60,60),color).save(content,'PNG')
                photos.append(m.add_upload(seller['user']['id'],content.getvalue(),angle)['id'])
            draft=m.save_draft(seller['user']['id'],dict(version=0,fields=dict(title=title,category='books',price='12.50',delivery='pickup',region='C1楼下',photos=photos)))
            return m.publish_draft(seller['user']['id'],draft['id'],draft['version'])['id']
        p1,p2,p3=listing('待下架教材甲'),listing('待下架教材乙'),listing('核查教材')
        case=m.create_ticket(buyer['user']['id'],dict(type='report',product_id=p3,subject='核查教材描述',body='请核对内页描述'))
        m.assign_ticket(admin['id'],case['id'],worker['id'],'排班')
        for i in range(23):
            m.create_ticket(buyer['user']['id'],dict(type='other',subject='咨询'+str(i),body='规则咨询'))
        order=m.checkout(buyer['user']['id'],dict(product_ids=[listing('退款教材')],delivery='pickup',appointment=time.time()+7200,key='refund'))
        m.order_action(buyer['user']['id'],order['id'],'pay',{})
        refund=m.create_ticket(buyer['user']['id'],dict(type='refund',order_id=order['id'],subject='未交付退款',body='双方同意取消'))
        base='http://127.0.0.1:'+str(server.server_port)
        errors=[]
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                def page_for(session):
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('response',lambda r: print('HTTP error',r.status,r.url,r.text()) if r.status>=400 else None)
                    page.goto(base,wait_until='networkidle')
                    page.evaluate('(token)=>sessionStorage.setItem("hc-token",token)',session['token'])
                    page.reload(wait_until='networkidle')
                    return page
                a=page_for(operator); w=page_for(support); b=page_for(buyer)
                for page,pid in [(a,p1),(w,p2)]:
                    page.goto(base+'/#product/'+str(pid),wait_until='networkidle')
                    button=page.get_by_role('button',name='下架商品',exact=True)
                    expect(button).to_be_visible()
                    assert button.evaluate('(el)=>getComputedStyle(el).color')=='rgb(185, 28, 28)'
                    button.click();page.locator('#moderate-product-form [name=reason]').fill('图片与商品描述不符')
                    page.get_by_role('button',name='确认下架',exact=True).click()
                    expect(page.locator('.detail-info > .tag')).to_contain_text('已下架')
                    assert m.product(pid)['removal_reason']=='staff_delist'
                b.goto(base+'/#product/'+str(p3),wait_until='networkidle')
                expect(b.get_by_role('button',name='下架商品',exact=True)).to_have_count(0)
                a.set_viewport_size({'width':390,'height':844})
                a.goto(base+'/#me',wait_until='networkidle')
                a.get_by_role('button',name='进入管理工作台',exact=True).click()
                expect(a.locator('[data-staff-navigation]')).to_be_visible()
                a.get_by_role('button',name='工单中心',exact=True).click()
                expect(a.locator('.ticket-row')).to_have_count(20)
                a.locator('#staff-queue-form [name=q]').fill('核查教材')
                a.get_by_role('button',name='筛选工单',exact=True).click()
                expect(a.locator('.ticket-row')).to_have_count(1)
                expect(a.locator('.ticket-row')).to_contain_text('客服小林')
                a.reload(wait_until='networkidle')
                expect(a.locator('#staff-queue-form [name=q]')).to_have_value('核查教材')
                a.locator('.ticket-row').click()
                expect(a.locator('[data-case-sources]')).to_contain_text('核查教材')
                expect(a.locator('[data-case-sources]')).to_contain_text('提交时快照')
                a.set_viewport_size({'width':1440,'height':1000})
                a.goto(base+'/#ticket/'+str(refund['id']),wait_until='networkidle')
                expect(a.locator('h1')).to_have_text('未交付退款')
                a.locator('#resolve-form [name=reason]').fill('双方协商，未交付全额退款')
                a.once('dialog',lambda d:d.dismiss())
                a.get_by_role('button',name='模拟退款',exact=True).click()
                assert m.order(admin['id'],order['id'])['status']=='disputed'
                a.once('dialog',lambda d:d.accept())
                a.get_by_role('button',name='模拟退款',exact=True).click()
                expect(a.locator('.support-case > section > .tag')).to_contain_text('已解决')
                assert m.order(admin['id'],order['id'])['status']=='refunded'
                m.resolve_ticket(admin['id'],case['id'],dict(outcome='resolved',reason='核实描述问题'))
                a.goto(base+'/#ticket/'+str(case['id']),wait_until='networkidle')
                a.get_by_role('button',name='处理卖家信誉',exact=True).click()
                expect(a.locator('#op-credit [name=ticket_id]')).to_have_value(str(case['id']))
                a.locator('#op-credit [name=rule_key]').select_option('hidden_defect')
                expect(a.locator('[data-credit-preview]')).to_contain_text('100 → 85')
                a.locator('#op-credit [name=reason]').fill('核实隐瞒重要缺页')
                a.once('dialog',lambda d:d.dismiss())
                a.get_by_role('button',name='记录信誉处理',exact=True).click()
                assert m.profile(seller['user']['id'])['score']==100
                a.once('dialog',lambda d:d.accept())
                a.get_by_role('button',name='记录信誉处理',exact=True).click()
                expect(a.locator('#op-credit')).to_have_count(0)
                assert m.profile(seller['user']['id'])['score']==85
                a.goto(base+'/#staff/audit',wait_until='networkidle')
                expect(a.locator('[data-audit-list]')).to_contain_text('商品下架')
                a.goto(base+'/#staff/overview',wait_until='networkidle')
                for width in [375,390,768,1440]:
                    a.set_viewport_size({'width':width,'height':900})
                    assert a.evaluate('document.documentElement.scrollWidth<=innerWidth')
                a.screenshot(path='/tmp/zj-admin-review/admin-updated.png',full_page=True)
                assert not errors,errors
                browser.close()
                print('Staff workspace Chromium: role-only red removal, seller notification, mobile entry, queue/filter persistence, source snapshot, refund/credit confirmation, audit and four widths passed')
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':run()
