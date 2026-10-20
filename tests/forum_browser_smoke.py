"""Exercise the refreshed forum in real Chrome with temporary data only."""
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))
from server import make_server

OUT=Path(os.environ.get('FORUM_SCREENSHOTS',tempfile.mkdtemp(prefix='forum-shots-')))
OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as data:
    server=make_server(data,0,trial=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    owner=server.market.register_password('13900000981','ForumTest2026','林同学')['user']['id']
    reader=server.market.register_password('13900000982','ForumTest2026','陈同学')['user']['id']
    now=time.time()
    bodies=[
      '用一个下午的摄影入门，交换一次吉他教学\n一直想学会用相机记录校园，也希望把自己会的东西分享出去。\n\n我能提供：构图、自然光人像和简单的照片整理。可以从手机摄影开始，不需要额外买设备。\n\n希望交换：吉他基础和弦与一首完整歌曲的练习。零基础，也接受和同学一起慢慢学。\n\n时间可以选在周末下午，地点在校内公共区域。感兴趣的同学可以先在楼里聊聊，我们一起确定计划。',
      '毕业前，一起整理一份校园生活指南\n关于学习、生活和那些好用的小经验，想听听大家的分享。',
      '想用视频剪辑经验，换一节水彩入门\n从一段校园短片开始，互相分享自己的经验。',
      '周五下午顺路去驿站，可以帮带小件快递\n写清大致时间和公共交接地点，沟通确认后再行动。',
      '周末一起练口语，交换你擅长的表达方式\n每次半小时，从介绍自己的校园生活开始。'
    ]
    with server.market.tx() as c:
        for i in range(26):
            body=bodies[i%5] if i<5 else f'第{i+1}期：一起分享实用的校园经验\n把自己熟悉的小技巧分享出来，也听听其他同学的想法。'
            c.execute('INSERT INTO posts(id,user_id,topic,body,created) VALUES(?,?,?,?,?)',(100+i,owner,'代拿快递' if i%5==3 else '交换人生',body,now-i*2500))
        for i in range(45):
            c.execute('INSERT INTO comments(id,post_id,user_id,body,created,parent_id) VALUES(?,?,?,?,?,?)',(1000+i,100,reader if i%2==0 else owner,'我也想参加，可以先从基础练习开始。时间和具体内容我们在这里商量。' if i%2==0 else '可以的，我们先确定一个适合大家的时间，再整理一下希望交流的内容。',now+i*30,1000 if i==2 else 0))
        c.execute('INSERT INTO wants(id,user_id,keyword,budget,description,status,created) VALUES(1,?,?,?, ?,?,?)',(owner,'数据结构教材 · 第二版',4500,'希望笔记不多、无缺页，可在校内公共区域交接。','open',now))
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROME_PATH',r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            def screenshot(name,full=False):
                expect(page.locator('#toast')).not_to_have_class(re.compile(r'.*\bshow\b.*'),timeout=6000)
                page.screenshot(path=str(OUT/name),full_page=full)
            page.on('pageerror',lambda e:errors.append(str(e)))
            base=f'http://127.0.0.1:{server.server_port}'
            page.goto(base,wait_until='networkidle')
            page.get_by_role('button',name='登录 / 注册',exact=True).click()
            page.locator('#login-form [name=phone]').fill('13900000982')
            page.locator('#login-form [name=password]').fill('ForumTest2026')
            page.get_by_role('button',name='登录',exact=True).click()
            expect(page.locator('.account-button')).to_contain_text('陈同学')
            page.goto(base+'/#forum',wait_until='networkidle')
            expect(page.locator('.forum-board-card')).to_have_count(3)
            assert page.locator('.forum-surface').evaluate('(el)=>getComputedStyle(el).color')=='rgb(37, 43, 52)'
            screenshot('forum-home-desktop.png',True)
            page.goto(base+'/#forum/exchange',wait_until='networkidle')
            expect(page.locator('#forum-feed .forum-post-row')).to_have_count(20)
            page.get_by_role('button',name='加载更多帖子',exact=True).click()
            expect(page.locator('#forum-feed .forum-post-row')).to_have_count(21)
            page.get_by_role('button',name='卡片布局',exact=True).click()
            expect(page.locator('#forum-feed')).to_have_attribute('data-layout','cards')
            page.get_by_role('button',name='列表布局',exact=True).click()
            page.get_by_role('button',name='热门',exact=True).click()
            expect(page.locator('.forum-post-title').first).to_contain_text('摄影入门')
            screenshot('forum-list-desktop.png',True)
            page.locator('#forum-search-form [name=q]').fill('水彩')
            page.locator('#forum-search-form button').click()
            expect(page.locator('.forum-post-row')).to_have_count(1)
            page.goto(base+'/#forum-post/100',wait_until='networkidle')
            expect(page.locator('.forum-original h1')).to_contain_text('摄影入门')
            expect(page.locator('.forum-reply')).to_have_count(20)
            page.locator('.forum-reply summary').first.click()
            expect(page.locator('.forum-reply').first).not_to_have_attribute('open','')
            page.locator('.forum-reply summary').first.click()
            page.get_by_role('button',name='加载更多回复',exact=True).click()
            expect(page.locator('.forum-reply')).to_have_count(40)
            page.get_by_role('button',name='加载更多回复',exact=True).click()
            expect(page.locator('.forum-reply')).to_have_count(45)
            page.evaluate('window.scrollTo(0,0)')
            screenshot('forum-detail-desktop.png')
            page.locator('[data-action=forum-target-reply]').first.click()
            expect(page.locator('#forum-reply-form')).to_have_attribute('data-parent','1000')
            page.locator('#forum-reply-body').fill('感谢分享，我也愿意从基础练习开始。')
            page.get_by_role('button',name='发布回复',exact=True).click()
            expect(page.locator('#forum-reply-count')).to_have_text('46')
            expect(page.locator('#forum-replies')).to_contain_text('感谢分享，我也愿意从基础练习开始。')
            page.goto(base+'/#forum-compose/exchange',wait_until='networkidle')
            page.locator('#forum-post-form [name=title]').fill('一起来练习校园人像摄影')
            page.locator('#forum-post-form [name=body]').fill('从构图和自然光开始，把各自熟悉的经验分享出来。')
            page.locator('#forum-post-form button[type=submit]').click()
            expect(page.locator('.forum-original h1')).to_have_text('一起来练习校园人像摄影')
            for name,url in [('home','#forum'),('list','#forum/errand'),('detail','#forum-post/100'),('account','#me'),('messages','#messages')]:
                page.set_viewport_size({'width':390,'height':844})
                page.goto(base+'/'+url,wait_until='networkidle')
                assert page.locator('body').evaluate('()=>document.documentElement.scrollWidth<=window.innerWidth'),url
                screenshot(f'forum-{name}-mobile.png')
            page.goto(base+'/#forum/errand',wait_until='networkidle')
            page.locator('#forum-search-form [name=q]').fill('驿站')
            page.locator('#forum-search-form button').click()
            expect(page.locator('.forum-post-row')).to_have_count(1)
            assert not errors,errors
            browser.close()
            print('PASS: home, lists/cards, global search/hot sort, post details, 20/40/45 replies, folding, reply attribution, publishing and mobile layouts')
            print('Screenshots:',OUT)
    finally:
        server.shutdown();server.server_close()
