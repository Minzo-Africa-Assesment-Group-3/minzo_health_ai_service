from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.assistant.service import AssistantService
from app.clients.current_user_api import CurrentUserApiClient
from app.clients.express_api import ExpressApiClient
from app.clients.moderation_api import ModerationApiClient
from app.core.config import Settings, get_settings
from app.llm import build_chat_model
from app.review_moderation.evaluation import ReviewEvaluationService
from app.review_moderation.service import ReviewModerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_express_api(request: Request) -> ExpressApiClient:
    return request.app.state.express_api


ExpressApiDep = Annotated[ExpressApiClient, Depends(get_express_api)]


def get_chat_model(settings: SettingsDep) -> ChatOpenAI:
    return build_chat_model(settings)


ChatModelDep = Annotated[ChatOpenAI, Depends(get_chat_model)]

user_bearer = HTTPBearer(auto_error=False, scheme_name="UserBearerAuth")


async def get_current_user_api(
    request: Request,
    express_api: ExpressApiDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(user_bearer)],
) -> CurrentUserApiClient | None:
    if not request.headers.get("Authorization"):
        return None
    if credentials is None or len(credentials.credentials.split()) != 1:
        raise HTTPException(status_code=401, detail={"code": "user_authentication_failed"})
    api = express_api.for_user(SecretStr(credentials.credentials))
    # Verify with Backend before enabling private tools. Body user IDs grant no access.
    await api.get_profile()
    return api


CurrentUserApiDep = Annotated[CurrentUserApiClient | None, Depends(get_current_user_api)]


def get_assistant_service(
    model: ChatModelDep,
    express_api: ExpressApiDep,
    current_user_api: CurrentUserApiDep,
) -> AssistantService:
    return AssistantService(model, express_api, current_user_api=current_user_api)


AssistantServiceDep = Annotated[AssistantService, Depends(get_assistant_service)]


def get_review_moderator(model: ChatModelDep, settings: SettingsDep) -> ReviewModerator:
    return ReviewModerator(
        model,
        model_name=settings.openai_model,
        policy_version=settings.moderation_policy_version,
        flag_confidence_threshold=settings.moderation_flag_confidence_threshold,
        block_confidence_threshold=settings.moderation_block_confidence_threshold,
    )


ReviewModeratorDep = Annotated[ReviewModerator, Depends(get_review_moderator)]


def get_moderation_callback(request: Request) -> ModerationApiClient:
    return request.app.state.moderation_callback


def get_review_evaluation_service(
    moderator: ReviewModeratorDep,
    callback: Annotated[ModerationApiClient, Depends(get_moderation_callback)],
) -> ReviewEvaluationService:
    return ReviewEvaluationService(moderator, callback)


ReviewEvaluationDep = Annotated[ReviewEvaluationService, Depends(get_review_evaluation_service)]
