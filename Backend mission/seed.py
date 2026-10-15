import json,time,html
from pathlib import Path

def seed(m,assets=None):
    if m.row('SELECT 1 FROM products LIMIT 1'):return
    books=[('计算机网络','谢希仁','第八版','电子工业出版社',1800,'#efae52','NETWORK'),('Python程序设计','董付国','第三版','清华大学出版社',1600,'#426c59','PYTHON'),('数据结构','严蔚敏','第二版','清华大学出版社',1200,'#64829c','DATA'),('高等数学 上册','同济大学','第七版','高等教育出版社',800,'#c97159','MATH'),('大学英语综合教程','李荫华','第二版','上海外语教育出版社',600,'#967eae','ENGLISH'),('操作系统概念','Silberschatz','第九版','高等教育出版社',2200,'#4e6975','SYSTEM')]
    assets=Path(assets) if assets is not None else Path(__file__).parent/'web'/'assets'
    assets.mkdir(parents=True,exist_ok=True)
    for i,(title,author,edition,publisher,price,color,english) in enumerate(books):
        fname=f'book{i}.svg'
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="650" viewBox="0 0 600 650"><rect width="600" height="650" fill="#f2eee5"/><ellipse cx="305" cy="568" rx="170" ry="17" fill="#ddd6c8"/><g transform="translate(135 72) rotate(-5 155 220)"><rect x="6" y="6" width="317" height="463" rx="6" fill="#ded6c7"/><rect width="310" height="455" rx="4" fill="{color}"/><rect x="15" width="2" height="455" fill="white" opacity=".35"/><text x="42" y="68" font-size="14" font-family="sans-serif" fill="white" opacity=".8">A CAMPUS SECOND CHAPTER</text><text x="40" y="135" font-size="28" font-family="sans-serif" fill="white">{html.escape(title)}</text><text x="42" y="177" font-size="16" font-family="sans-serif" fill="white">{edition} · {html.escape(author)}</text><path d="M40 235H270M40 258H220M40 281H245" stroke="white" opacity=".35" stroke-width="2"/><text x="38" y="365" font-size="34" font-family="sans-serif" fill="white" font-weight="bold">{english}</text><text x="40" y="415" font-size="13" font-family="sans-serif" fill="white">演示封面 · 非商品实拍</text></g></svg>'''
        (assets/fname).write_text(svg)
        data={'description':'演示商品，用于体验软件流程。实际购买前请检查版次、笔记、缺页及附件。图片是原创示意封面，不是实拍。','author':author,'edition':edition,'publisher':publisher,'notes':'少量笔记' if i%2==0 else '无笔记','missing':'无缺页','accessories':'无附件','condition':'有使用痕迹','bought':'2024-09','college':'计算机工程学院','major':'计算机科学与技术','original_price':4500,'simulation':True,'photos':[{'url':'/assets/'+fname,'angle':a} for a in ['front','side','top']]}
        with m.tx() as c:c.execute('INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created) VALUES(?,?,?,?,?,?,?,?,?)',(1 if i<4 else 2,title,'books',price,200,'both','A1楼下入口',json.dumps(data,ensure_ascii=False),time.time()-i*3200))
    for i,(name,price,shape) in enumerate([('毕业出 · 可折叠小凳子',1000,'chair'),('护眼台灯，三档亮度',1500,'lamp'),('入门羽毛球拍，附拍套',2500,'racket')]):
        color=['#cc8966','#88a29a','#79879d'][i]
        shapes={'chair':'<path d="M175 260H420V310H175zM200 310L160 520M395 310L440 520M200 310L405 500M395 310L190 500" fill="#d4ad7c" stroke="#765f49" stroke-width="13"/>','lamp':'<path d="M220 490H400M310 480L340 330L260 210" stroke="#465556" stroke-width="22" fill="none"/><path d="M180 250Q180 130 300 160L330 230Z" fill="#e3b552"/>','racket':'<ellipse cx="300" cy="260" rx="105" ry="145" fill="none" stroke="#455b54" stroke-width="15"/><path d="M300 405V560" stroke="#bd7c4e" stroke-width="22"/><path d="M240 150V365M270 130V390M300 120V400M330 130V390M360 150V365M205 200H395M195 250H405M205 300H395M230 350H370" stroke="#99a9a0" stroke-width="2"/>'}
        f=f'item{i}.svg';(assets/f).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="650"><rect width="600" height="650" fill="#eceee9"/>{shapes[shape]}<text x="170" y="620" fill="#777" font-size="18">演示插画 · 非商品实拍</text></svg>')
        data={'description':'毕业整理宿舍，希望它在新的角落继续发挥作用。演示商品，非真实出售。','photos':[{'url':'/assets/'+f,'angle':a} for a in ['front','side','top']],'simulation':True,'condition':'正常使用痕迹','college':'计算机工程学院','bought':'2025-03','original_price':5000}
        with m.tx() as c:c.execute('INSERT INTO products(seller_id,title,category,price,delivery_fee,delivery,region,data,created) VALUES(?,?,?,?,?,?,?,?,?)',(2,name,'sports' if i==2 else 'living',price,300,'both','L17楼下入口',json.dumps(data,ensure_ascii=False),time.time()-i*1500))
    with m.tx() as c:
        c.execute('INSERT INTO posts(user_id,topic,body,created) VALUES(?,?,?,?)',(1,'求购','演示帖子：想找一本第八版计算机网络，有合适的同学可以分享商品。',time.time()))
        c.execute('INSERT INTO posts(user_id,topic,body,created) VALUES(?,?,?,?)',(2,'毕业季','演示帖子：毕业不散场，让书和小物件去下一个同学的角落。',time.time()-1800))
