"""Export a standalone, read-only site from fresh fictional seed data only."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Backend mission'))
from app.market import Market
from app.seed import seed
from app.core.config import WEB


def build(output):
    """从全新合成快照与相对路径 Vue 构建导出只读演示，不修改源码或既有目录。"""
    output=Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Choose a new or empty output directory; existing files will not be overwritten.')
    # Never open var/, accept an input database, or export application accounts.
    with tempfile.TemporaryDirectory() as tmp:
        market=Market(tmp)
        seed(market,assets=Path(tmp)/'assets')
        products=market.products()
        profiles={}
        for uid in sorted({p['seller_id'] for p in products}):
            user=market.profile(uid)
            profiles[str(uid)]={k:user[k] for k in ['id','nickname','college','major','education','bio','score']}
        data={'config':{'name':'华立转角','simulation':True,'public_demo':True,'campus':'广州校区','pilot':'计算机工程学院','support_hours':'08:00–20:00','colleges':[]},
              'products':products,'profiles':profiles,'posts':market.posts(),'comments':{}}
    output.mkdir(parents=True,exist_ok=True)
    npm=shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise ValueError('需要项目本机 Node/npm，请先在 web 7M 执行 npm ci。')
    # 临时产物使用相对 base，既能放根路径，也能放 GitHub Pages 子目录。
    # 不复制 SFC、node_modules、包配置或未编译的裸模块导入。
    with tempfile.TemporaryDirectory() as build_tmp:
        bundle=Path(build_tmp)/'web'
        subprocess.run([npm,'run','build','--','--base=./','--outDir',str(bundle)],cwd=WEB,check=True)
        shutil.copytree(bundle,output,dirs_exist_ok=True,ignore=shutil.ignore_patterns('miniprogram'))
    shutil.copy2(WEB/'public-demo.js',output/'public-demo.js')
    html=(output/'index.html').read_text(encoding='utf-8')
    # 注意：不要匹配到结尾的引号。资源引用带 ?v= 版本号查询串，
    # 写成 src="/src/main.js" 会在加版本号之后失配，导致下面 public-demo.js 注入不进去。
    html=html.replace('href="/','href="./').replace('src="/','src="./')
    # 演示版只留只读快照：public-demo.js 提供假的 api()，必须比主模块先执行。
    # 经典 defer 脚本与 module 脚本都按文档顺序执行，所以先后是有保证的。
    html=html.replace('<script type="module"','<script src="./public-demo.js" defer></script><script type="module"',1)
    html=html.replace('</head>','<meta name="robots" content="noindex,nofollow"></head>')
    (output/'index.html').write_text(html,encoding='utf-8')
    css=(output/'market.css').read_text(encoding='utf-8').replace("url('/assets/","url('./assets/")
    (output/'market.css').write_text(css,encoding='utf-8')
    for product in products:
        for photo in product['photos']:photo['url']='.'+photo['url']
    (output/'demo-data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (output/'_headers').write_text("/*\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: DENY\n  Referrer-Policy: same-origin\n  Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'self'\n",encoding='utf-8')
    (output/'.nojekyll').touch()
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='New or empty directory for static hosting')
    args=parser.parse_args()
    try:result=build(args.output)
    except ValueError as error:parser.error(str(error))
    print('Public demo exported to '+str(result))
