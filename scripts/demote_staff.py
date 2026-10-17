"""Local demotion tool. Run with --data, or choose the live project/data folder."""
import argparse
import importlib.util
import sqlite3
from pathlib import Path


def choose_directory():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return input('输入现用项目根目录或数据目录的完整路径：').strip().strip('"')
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            return filedialog.askdirectory(title='选择正在使用的转角项目根目录或 var-trial 数据目录')
        finally:
            root.destroy()
    except tk.TclError:
        return input('输入现用项目根目录或数据目录的完整路径：').strip().strip('"')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', help='现用项目目录、数据目录或 market.sqlite3 文件')
    parser.add_argument('--nickname', default='godfly')
    parser.add_argument('--user-id', type=int)
    args = parser.parse_args()
    selected = args.data or choose_directory()
    if not selected:
        print('已取消，未修改账号。')
        return
    folder = Path(selected).resolve()
    candidates = [folder] if folder.is_file() else [folder / 'market.sqlite3', folder / 'var-trial' / 'market.sqlite3']
    databases = [path for path in candidates if path.is_file()]
    if len(databases) != 1:
        parser.error('未找到唯一的现用数据库，请直接选择 var-trial 数据目录')
    here = Path(__file__).resolve().parent
    modules = [here / 'roles.py', here.parent / 'Backend mission' / 'app' / 'staff' / 'roles.py']
    module_path = next((path for path in modules if path.is_file()), None)
    if module_path is None:
        parser.error('降权工具文件不完整，请将工具包完整解压后运行')
    spec = importlib.util.spec_from_file_location('zhuanjiao_local_roles', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        result = module.demote_account(databases[0], args.nickname, args.user_id)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.error(str(error))
    if not result['changed']:
        print('账号 ' + result['nickname'] + ' 已经是普通用户，未重复修改。')
        return
    print('成功：' + result['nickname'] + '（ID ' + str(result['id']) + '）已降为普通用户。')
    print('已撤销旧登录会话：' + str(result['revoked_sessions']))
    print('退回未处理工单：' + str(result['released_tickets']))
    print('修改前备份：' + result['backup_path'])
    print('账号、商品、订单、密码和信誉记录保留。重新登录后使用普通用户权限。')


if __name__ == '__main__':
    main()
