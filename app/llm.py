from fastapi import HTTPException, status
from langchain_openai import ChatOpenAI

from app.core.config import Settings


def build_chat_model(settings: Settings) -> ChatOpenAI:
    api_key = (
        settings.openai_api_key.get_secret_value().strip()
        if settings.openai_api_key is not None
        else ""
    )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=api_key,
        temperature=0,
        timeout=30,
        max_retries=2,
    )
