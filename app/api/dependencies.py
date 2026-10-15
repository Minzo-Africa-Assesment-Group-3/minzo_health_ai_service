from typing import Annotated

from fastapi import Depends, Request
from langchain_openai import ChatOpenAI

from app.assistant.service import AssistantService
from app.clients.express_api import ExpressApiClient
from app.core.config import Settings, get_settings
from app.llm import build_chat_model
from app.review_moderation.service import ReviewModerator

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_express_api(request: Request) -> ExpressApiClient:
    return request.app.state.express_api


ExpressApiDep = Annotated[ExpressApiClient, Depends(get_express_api)]


def get_chat_model(settings: SettingsDep) -> ChatOpenAI:
    return build_chat_model(settings)


ChatModelDep = Annotated[ChatOpenAI, Depends(get_chat_model)]


def get_assistant_service(
    model: ChatModelDep,
    express_api: ExpressApiDep,
) -> AssistantService:
    return AssistantService(model, express_api)


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
