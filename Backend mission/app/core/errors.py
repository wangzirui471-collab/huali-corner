"""业务异常与输入校验。

Java 对应：各模块共用的 exception + validator。
require / text / cents 原本是 Market 上的静态方法，现提到这里作为公共基类，
所有 service 继承 ValidationMixin 后仍可写 self.require(...)。
"""


class DomainError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status


class ValidationMixin:
    """所有 service 的公共基类。只放与业务无关的通用校验。"""

    @staticmethod
    def require(ok,message,status=400):
        if not ok:raise DomainError(message,status)
    @staticmethod
    def text(v,maxlen,label):
        ValidationMixin.require(isinstance(v,str) and 0<len(v.strip())<=maxlen,f'{label}需填写且不超过{maxlen}字')
        return v.strip()
    @staticmethod
    def cents(v,label='金额'):
        ValidationMixin.require(type(v) is int and 0<=v<=1000000,f'{label}须为0至10000元之间的整数分');return v
