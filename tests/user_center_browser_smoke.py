"""Opt-in real browser contract for A after all public wiring is integrated.

B only writes/reads this source. Running --run creates isolated synthetic data;
do not run this script on the user's machine without their authorization.
"""

import argparse
import gc
import io
from pathlib import Path
import sys
import tempfile
import threading


def run(output: Path, chromium: str | None = None) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend mission'))
    from PIL import Image
    from playwright.sync_api import expect, sync_playwright
    from server import make_server

    expect.set_options(timeout=10000)
    temporary = tempfile.TemporaryDirectory(prefix='zj-user-center-browser-')
    server = None
    worker = None
    try:
        server = make_server(temporary.name, 0, trial=True)
        market = server.market
        if not all(hasattr(market,name) for name in ['user_profile','user_set_avatar','user_avatar_bytes']):
            raise RuntimeError('A must integrate UserProfiles, UserAvatars and migrations before this test')
        password = 'UserCenterSecret2026!'
        first = market.register_password('13900000601',password,'甲同学')
        second = market.register_password('13900000602',password,'乙同学')
        market.bootstrap_admin('13900000600',password)
        worker = threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        output.mkdir(parents=True,exist_ok=True)
        errors = []

        with sync_playwright() as playwright:
            options = {'headless':True}
            if chromium:
                options['executable_path'] = chromium
            browser = playwright.chromium.launch(**options)
            page = browser.new_page(viewport={'width':390,'height':900})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())

            def login(phone):
                page.locator('[data-action="login"]').click()
                form = page.locator('#login-form')
                form.locator('[name="phone"]').fill(phone)
                form.locator('[name="password"]').fill(password)
                form.locator('button[type="submit"],button:not([type])').last.click()
                expect(page.locator('[data-action="login"]')).to_have_count(0)
                page.goto(base+'/#me')
                expect(page.locator('#user-profile-form')).to_be_visible()

            page.goto(base,wait_until='networkidle')
            login('13900000601')
            assert page.locator('link[href*="user-center.css"]').count(), 'A must register user-center.css'
            form = page.locator('#user-profile-form')
            form.locator('[name="degree_level"]').select_option('junior_college')
            form.locator('[name="study_status"]').select_option('graduated')
            text = '<img src=x onerror="window.__profileXss=1">'
            form.locator('[name="bio"]').fill(text)
            form.locator('button[type="submit"]').click()
            expect(page.locator('[data-user-profile-feedback]')).to_contain_text('资料已保存')
            page.reload(wait_until='networkidle')
            expect(page.locator('[name="degree_level"]')).to_have_value('junior_college')
            expect(page.locator('[name="study_status"]')).to_have_value('graduated')
            expect(page.locator('[data-user-summary]')).to_contain_text(text)
            assert page.evaluate('window.__profileXss') is None

            # Public profile is a real endpoint and must not expose private fields.
            public = page.request.get(base+'/api/profile?id='+str(first['user']['id'])).json()
            assert set(public) == {'user','products'}
            assert not ({'phone','address','password','digest','recovery_digest','is_active'} & set(public['user']))
            page.goto(base+'/#profile/'+str(first['user']['id']))
            expect(page.get_by_role('button',name='编辑我的资料',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='发私信',exact=True)).to_have_count(0)
            assert not page.locator('.user-center script').count()
            page.goto(base+'/#me')

            # Real 409: another writer commits after this form has read its version.
            form = page.locator('#user-profile-form')
            form.locator('[name="bio"]').fill('保留我的输入')
            latest = market.user_profile(first['user']['id'])
            market.user_update_profile(first['user']['id'],{'profile_version':latest['profile_version'],
                                                          'bio':'服务器较新资料'})
            form.locator('button[type="submit"]').click()
            expect(page.locator('[data-user-profile-feedback]')).to_contain_text('输入仍保留')
            expect(form.locator('[name="bio"]')).to_have_value('保留我的输入')
            page.locator('[data-action="user-profile-compare"]').click()
            expect(page.locator('[data-user-comparison]')).to_contain_text('服务器较新资料')
            page.screenshot(path=str(output/'conflict-mobile.png'),full_page=True)
            page.locator('[data-action="user-profile-keep-input"]').click()
            form.locator('button[type="submit"]').click()
            expect(page.locator('[data-user-profile-feedback]')).to_contain_text('资料已保存')

            avatar = page.locator('#user-avatar-form')
            image_bytes = io.BytesIO()
            with Image.new('RGB',(120,80),'coral') as image:
                image.save(image_bytes,'PNG')
            avatar.locator('[name="avatarfile"]').set_input_files({
                'name':'synthetic-avatar.png','mimeType':'image/png','buffer':image_bytes.getvalue()})
            avatar.locator('button[type="submit"]').click()
            expect(page.locator('[data-user-avatar-feedback]')).to_contain_text('仅你可见')
            upload_id = avatar.locator('[name="upload_id"]').input_value()
            assert page.request.get(base+'/media/'+upload_id).status == 403
            page.locator('[data-action="user-avatar-confirm"]').click()
            expect(page.locator('[data-user-avatar-feedback]')).to_contain_text('头像已更新')
            assert page.request.get(base+'/media/'+upload_id).status == 200
            page.locator('[data-action="user-avatar-remove"]').click()
            expect(page.locator('[data-user-avatar-feedback]')).to_contain_text('恢复默认')
            assert page.request.get(base+'/media/'+upload_id).status == 403

            # Invalid bytes with a PNG name/type still have to fail on the server.
            avatar.locator('[name="avatarfile"]').set_input_files({
                'name':'fake.png','mimeType':'image/png','buffer':b'not a real PNG'})
            avatar.locator('button[type="submit"]').click()
            expect(page.locator('[data-user-avatar-feedback]')).to_contain_text('有效')
            page.screenshot(path=str(output/'upload-failure-mobile.png'),full_page=True)

            # Hold a real old-session save, log out, then sign in as another user.
            held = []

            def delay_profile(route):
                if route.request.method == 'POST' and not held:
                    # Commit the real old-session save while it is authorized,
                    # but withhold its successful response from the page.
                    response = route.fetch()
                    assert response.status == 200
                    held.append((route,response))
                else:
                    route.continue_()

            page.route('**/api/user/profile',delay_profile)
            page.evaluate('window.__oldUserRoot = document.querySelector("[data-user-center]")')
            form.locator('[name="bio"]').fill('旧会话不可写回乙账号')
            form.locator('button[type="submit"]').click()
            page.wait_for_function('document.querySelector("[data-user-center]")?.dataset.userBusy === "1"')
            page.locator('[data-action="logout"]').click()
            expect(page.locator('[data-action="login"]')).to_be_visible()
            login('13900000602')
            assert held, 'request must be intercepted before account switching'
            with page.expect_response(lambda response:response.request.method=='POST'
                                      and response.url==base+'/api/user/profile') as delivered:
                held[0][0].fulfill(response=held[0][1])
            delivered.value.finished()
            page.wait_for_function('!window.__oldUserRoot.dataset.userBusy')
            expect(page.locator('[data-user-summary]')).to_contain_text('乙同学')
            expect(page.locator('[name="bio"]')).not_to_have_value('旧会话不可写回乙账号')
            assert page.evaluate('async () => (await import("/src/core/state.js")).state.me.id') == second['user']['id']
            assert market.user_profile(first['user']['id'])['bio'] == '旧会话不可写回乙账号'
            assert market.user_profile(second['user']['id'])['bio'] != '旧会话不可写回乙账号'
            page.evaluate('delete window.__oldUserRoot')
            page.unroute('**/api/user/profile',delay_profile)

            for route in ['me','profile/'+str(second['user']['id'])]:
                page.goto(base+'/#'+route)
                for width in [375,390,768,1440]:
                    page.set_viewport_size({'width':width,'height':900})
                    expect(page.locator('.user-center')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (route,width)
                    page.screenshot(path=str(output/(route.split('/')[0]+'-'+str(width)+'.png')),full_page=True)

            page.goto(base+'/#me')
            for destination in ['orders','favorites','listings']:
                expect(page.locator('.user-center [data-go="'+destination+'"]').first).to_be_visible()
            expect(page.locator('[data-action="appeal"]')).to_be_visible()
            expect(page.locator('[data-action="change-password"]')).to_be_visible()
            page.locator('[data-action="logout"]').click()
            login('13900000600')
            expect(page.locator('.user-center [data-go="staff"]')).to_be_visible()
            page.locator('.user-center [data-go="staff"]').click()
            expect(page.locator('.staff-app')).to_be_visible()
            assert not errors, errors
            browser.close()
    finally:
        if server is not None:
            if worker is not None:
                server.shutdown()
                worker.join(timeout=5)
            server.server_close()
        gc.collect()
        temporary.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Explicitly authorize synthetic local database/browser checks')
    parser.add_argument('--output',type=Path,default=Path('artifacts/user-center'))
    parser.add_argument('--chromium')
    args = parser.parse_args()
    if not args.run:
        parser.error('This opt-in script creates synthetic databases; A/user must explicitly pass --run')
    run(args.output,args.chromium)
