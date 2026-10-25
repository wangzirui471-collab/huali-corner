"""公开 FAQ 的协议路由，仅把严格输入和原 Bearer 交给应用服务。"""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from huali.modules.support.assistant.schema import AnswerData, AnswerInput
from huali.modules.support.assistant.service import AssistantService
from huali.transport.contracts import Envelope


def create_assistant_router(service: AssistantService) -> APIRouter:
    """由 bootstrap 注入用例，路由内不创建模型 SDK、网关或数据库。"""
    router = APIRouter(prefix="/api/v1/support/assistant", tags=["support"])

    @router.post("/answer", response_model=Envelope[AnswerData])
    async def answer(
        data: AnswerInput,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Envelope[AnswerData]:
        """处理一次公开提问；不信任客户端自报用户或角色。"""
        token = ""
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        result = await service.answer(token, str(data.client_turn_id), data.question)
        return Envelope[AnswerData](
            code="OK", message="成功", data=result, request_id=request.state.request_id
        )

    return router
