"""应用组合根：把各模块的 service 拼成一个可用的应用对象。

Java 里由 Spring 容器负责装配，Python 这里用多继承显式拼装。
各 service 之间可以互相调用（例如 trade 调 catalog 的 product()），
因为它们在同一个实例上，方法按 MRO 解析。

模块划分：
    core       基础设施：路径、数据库、异常与校验
    account    账号
    catalog    商品
    trade      交易
    community  社区
    support    客服
    notifications 站内通知
    staff      人员与权限（平台侧账号）
    moderation 内容审核（词库 + 扫描 + 词库维护）
    ops        运维

路由层在 Backend mission/server.py，不在包内 —— 它只做 HTTP 解析与转发。
"""

from .core.database import Store
from .core.errors import DomainError, ValidationMixin
from .account.service import AccountService
from .account.profiles import UserProfiles
from .account.avatars import UserAvatars
from .catalog.service import CatalogService
from .trade.service import TradeService
from .notifications.service import NotificationService
from .community.service import CommunityService
from .support.service import SupportService
from .staff.service import StaffService
from .moderation.service import ModerationService
from . import moderation
from .ops.service import OpsService
from pathlib import Path


class Market(Store, AccountService, UserProfiles, UserAvatars, CatalogService, TradeService,
             NotificationService, CommunityService, SupportService, StaffService,
             ModerationService, OpsService):
    """试用版应用的组合根。"""

    def __init__(self,root,trial=False):
        self.trial=trial;super().__init__(root)
        # 词库的运行时覆盖目录跟着数据目录走：
        # 同一份代码跑 var / var-trial 两个实例时，运营在试用版改的词条
        # 不会影响另一份数据；改动的文件也不进 git。
        moderation.configure(self.root/'moderation')
        with self.tx() as c:
            mode='trial' if trial else 'demo';previous=c.execute("SELECT value FROM settings WHERE key='auth_mode'").fetchone()
            self.require(not previous or previous['value']==mode,'演示和学院试用必须使用不同的数据目录',409)
            self.require(previous or not trial or not c.execute('SELECT 1 FROM users LIMIT 1').fetchone(),'旧演示数据不能用作试用账号库，请指定新的数据目录',409)
            c.execute("INSERT OR IGNORE INTO settings VALUES('auth_mode',?)",(mode,))
            for upload in c.execute('SELECT id,path FROM uploads').fetchall():
                local=self.root/'uploads'/Path(upload['path']).name
                if local.exists():c.execute('UPDATE uploads SET path=? WHERE id=?',(str(local),upload['id']))
            for phone,nick,role in ([] if trial else [('13800000001','林同学','user'),('13800000002','小陈同学','user'),('19065322759','转角客服','admin')]):
                c.execute('INSERT OR IGNORE INTO users(phone,nickname,role,major) VALUES(?,?,?,?)',(phone,nick,role,'计算机科学与技术'))


__all__ = ['Market', 'DomainError', 'ValidationMixin']
