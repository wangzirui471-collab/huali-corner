"""Real Chromium: seller fixes, private chat, linked review and campus help."""
import io
from datetime import datetime,timedelta,timezone
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Backend mission'))
from server import make_server
from PIL import Image
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=10000)


def run():
 with tempfile.TemporaryDirectory() as root:
  server=make_server(root,0,trial=True);threading.Thread(target=server.serve_forever,daemon=True).start()
  m=server.market
  admin=m.bootstrap_admin('13900000500','OperatorPassword2026!')
  seller=m.register_password('13900000501','SellerPassword2026!','互助发布者')
  buyer=m.register_password('13900000502','BuyerPassword2026!','买家同学')
  m.create_support(admin['id'],dict(phone='13900000503',password='WorkerPassword2026!',nickname='客服甲'))
  worker=m.login_password('13900000503','WorkerPassword2026!')
  def order():
   photos=[]
   for angle,color in [('front','red'),('side','green'),('top','blue')]:
    data=io.BytesIO();Image.new('RGB',(50,50),color).save(data,'PNG');photos.append(m.add_upload(seller['user']['id'],data.getvalue(),angle)['id'])
   draft=m.save_draft(seller['user']['id'],dict(version=0,fields=dict(title='测试教材',category='books',price='12',delivery='pickup',region='C1楼下',photos=photos)))
   product=m.publish_draft(seller['user']['id'],draft['id'],draft['version'])
   return m.checkout(buyer['user']['id'],dict(product_ids=[product['id']],delivery='pickup',appointment=time.time()+7200,key=str(time.time_ns())))
  tomorrow=(datetime.now(timezone(timedelta(hours=8)))+timedelta(days=1)).strftime('%Y-%m-%dT18:00')
  base='http://127.0.0.1:'+str(server.server_port);errors=[];failures=[];checks=[]
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    def page_for(session):
     page=browser.new_page(viewport={'width':390,'height':844})
     page.on('pageerror',lambda error:errors.append(str(error)))
     page.on('response',lambda response:failures.append((response.status,response.url)) if response.status>=400 else None)
     page.on('dialog',lambda dialog:dialog.accept())
     page.goto(base,wait_until='networkidle');page.evaluate('(token)=>sessionStorage.setItem("hc-token",token)',session['token']);page.reload(wait_until='networkidle');return page
    a=page_for(seller);b=page_for(buyer)
    o=order();a.goto(base+'/#orders');a.get_by_role('button',name='修改订单',exact=True).click()
    expect(a.locator('#order-edit-form')).to_have_attribute('data-role','seller')
    expect(a.locator('#order-edit-form [name=delivery]')).to_have_count(0)
    a.locator('#order-edit-form [name=appointment]').fill(tomorrow)
    a.get_by_role('button',name='保存修改',exact=True).click();expect(a.locator('#order-edit-form')).to_have_count(0)
    a.get_by_role('button',name='取消订单',exact=True).click();expect(a.locator('.order-top')).to_contain_text('已取消')
    assert m.notifications(buyer['user']['id'])['items'][0]['title']=='卖家已取消订单';checks.append('卖家改单/取消/通知')
    a.goto(base+'/#community');a.get_by_role('button',name='逛逛互助／发布需求').click()
    a.get_by_role('button',name='发布需求／提供服务',exact=True).click()
    a.locator('#help-post-form [name=title]').fill('今晚帮取快递')
    a.locator('#help-post-form [name=reward_yuan]').fill('3.50')
    a.locator('#help-post-form [name=place]').fill('C1楼下公共入口')
    a.locator('#help-post-form [name=deadline]').fill(tomorrow)
    a.locator('#help-post-form [name=body]').fill('小件，取件码私聊提供')
    a.get_by_role('button',name='发布互助信息',exact=True).click();expect(a.locator('.help-card')).to_contain_text('今晚帮取快递')
    post_id=int(a.url.split('/')[-1]);assert m.help_post(post_id)['reward']==350
    b.goto(base+'/#help');b.get_by_role('button',name='私聊协商').click()
    expect(b.locator('.chat-title')).to_contain_text('互助发布者')
    b.locator('#message-form [name=message]').fill('我可以帮忙')
    b.locator('#message-form button').click();expect(b.locator('#chat-stream')).to_contain_text('我可以帮忙')
    room=m.rooms(seller['user']['id'])['joined'][0]
    assert room['unread_count']==1
    a.goto(base+'/#messages/'+str(room['id']));expect(a.locator('.chat-title')).to_contain_text('买家同学')
    expect(a.locator('#chat-stream')).to_contain_text('我可以帮忙')
    a.wait_for_function('!document.querySelector("[data-room-buttons]").textContent.includes("条未读")')
    assert m.rooms(seller['user']['id'])['joined'][0]['unread_count']==0;checks.append('互助发布/私聊/名称/已读')
    b.goto(base+'/#help/'+str(post_id));b.get_by_role('button',name='客服反馈',exact=True).click()
    b.locator('#ticket-form [name=body]').fill('需要了解互助规则')
    b.get_by_role('button',name='提交反馈',exact=True).click();expect(b.locator('h1')).to_contain_text('校园互助')
    ticket_id=int(b.url.split('/')[-1]);assert m.ticket(buyer['user']['id'],ticket_id)['post_id']==post_id
    work=page_for(worker);work.goto(base+'/#ticket/'+str(ticket_id))
    expect(work.get_by_text('未分配给你的工单',exact=False)).to_be_visible()
    work.locator('[name=reason]').fill('认领互助反馈');work.get_by_role('button',name='认领后查看详情').click()
    expect(work.locator('.support-case > section > .description')).to_contain_text('需要了解互助规则')
    m.resolve_ticket(admin['id'],ticket_id,dict(outcome='resolved',reason='已答复规则'))
    b.reload();expect(b.locator('#op-case-reply')).to_have_count(0)
    b.get_by_role('button',name='提交关联申诉／新材料').click()
    b.locator('#ticket-form [name=subject]').fill('申请复核')
    b.locator('#ticket-form [name=body]').fill('补充新材料')
    b.get_by_role('button',name='提交反馈',exact=True).click();expect(b.locator('h1')).to_contain_text('申请复核')
    appeal_id=int(b.url.split('/')[-1]);assert m.ticket(buyer['user']['id'],appeal_id)['related_ticket_id']==ticket_id
    checks.append('关联反馈/认领权限/结案关联申诉')
    a.goto(base+'/#help/'+str(post_id));a.get_by_role('button',name='关闭需求',exact=True).click()
    expect(a.locator('.help-card')).to_contain_text('已关闭')
    b.goto(base+'/#help');expect(b.locator('.help-card')).to_have_count(0);checks.append('作者关闭与公开招募过滤')
    for width in [375,390,768,1440]:
     b.set_viewport_size({'width':width,'height':900});assert b.evaluate('document.documentElement.scrollWidth<=innerWidth')
    a.evaluate('id=>{localStorage.setItem("zj-draft-"+id,"private");localStorage.setItem("zj-edit-"+id+"-1","private");}',seller['user']['id'])
    a.goto(base+'/#me');a.locator('[data-action=logout]').click();expect(a.locator('[data-action=login]').first).to_be_visible()
    assert not a.evaluate('id=>localStorage.getItem("zj-draft-"+id)||localStorage.getItem("zj-edit-"+id+"-1")',seller['user']['id'])
    checks.append('响应式与真实退出缓存清理')
    assert not errors,errors;assert not failures,failures
    browser.close();print('Functional/help Chromium journeys passed:',len(checks),'; '.join(checks))
  finally:server.shutdown();server.server_close()

if __name__=='__main__':run()
