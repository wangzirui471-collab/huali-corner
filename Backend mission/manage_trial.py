"""Local/server-operator account management; never exposed through the website."""
import argparse
import getpass
import os
import time
from pathlib import Path
from app.market import Market,DomainError
from app.core.config import data_dir


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create-admin','reset-password'])
    parser.add_argument('--data',default=os.environ.get('HUALI_DATA_DIR') or data_dir(True))
    args=parser.parse_args()
    phone=input('手机号（仅作账号，不验证号码归属）：').strip()
    password=getpass.getpass('新密码（12至128个字符）：')
    confirmation=getpass.getpass('再次输入新密码：')
    if password!=confirmation:parser.error('两次密码不一致')
    try:
        market=Market(args.data,trial=True)
        if args.action=='create-admin':
            result=market.bootstrap_admin(phone,password)
            print('管理员已配置，账号ID：'+str(result['id'])+'。若已存在，不会覆盖原密码。')
        else:
            market._phone(phone);market._password(password)
            user=market.row('SELECT id FROM users WHERE phone=?',(phone,))
            market.require(user,'账号不存在',404)
            salt,digest,rounds,recovery_digest,recovery=market._new_credential(password)
            with market.tx() as c:
                c.execute('UPDATE password_credentials SET salt=?,digest=?,rounds=?,recovery_digest=? WHERE user_id=?',(salt,digest,rounds,recovery_digest,user['id']))
                c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                c.execute('DELETE FROM auth_attempts WHERE phone=?',(phone,))
                c.execute('INSERT INTO audit(target,type,reason,created) VALUES(?,?,?,?)',(user['id'],'operator_password_reset','服务器操作者通过本地管理命令重置密码',time.time()))
            print('密码已重置，所有登录会话已失效。请将下列新恢复码私下交给账号本人：')
            print(recovery)
    except DomainError as error:parser.error(str(error))


if __name__=='__main__':main()
