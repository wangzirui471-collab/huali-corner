"""交易模块入口：组合订单与账本两个领域服务。

具体实现：
    orders.py  订单创建、状态流转、付款前改单、超时关闭
    ledger.py  模拟账本流水与撮合服务费

保留 ``TradeService`` 是为了让 ``Market`` 组合根和既有调用方无需改动；
它不是新的一层抽象，只是把两个领域混入拼在一起。
"""
from .ledger import LedgerService
from .orders import OrderService


class TradeService(OrderService, LedgerService):
    """交易领域组合入口。"""
