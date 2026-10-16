"""Export a standalone, read-only site from fresh fictional seed data only."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from market import Market
from seed import seed


def build(output):
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
        data={'config':{'name':'转角','simulation':True,'public_demo':True,'campus':'广州校区','pilot':'计算机工程学院','support_hours':'08:00–20:00','colleges':[]},
              'products':products,'profiles':profiles,'posts':market.posts(),'comments':{}}
    output.mkdir(parents=True,exist_ok=True)
    for name in ['app.js','public-demo.js','publishing.js','operations.js','styles.css','market.css','publishing.css','locations.js','inbox.js','inbox.css']:
        shutil.copy2(ROOT/'web'/name,output/name)
    assets=output/'assets';assets.mkdir(exist_ok=True)
    for name in ['market-demo-photos.png']+['book%d.svg'%n for n in range(6)]+['item%d.svg'%n for n in range(3)]:
        shutil.copy2(ROOT/'web/assets'/name,assets/name)
    html=(ROOT/'web/index.html').read_text(encoding='utf-8')
    html=html.replace('href="/','href="./').replace('src="/','src="./')
    html=html.replace('<script src="./app.js"','<script src="./public-demo.js" defer></script><script src="./app.js"')
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
