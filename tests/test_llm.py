import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.llm import build_chat_model


def test_empty_openai_key_is_reported_as_unavailable() -> None:
    settings = Settings(_env_file=None, openai_api_key="")

    with pytest.raises(HTTPException) as captured:
        build_chat_model(settings)

    assert captured.value.status_code == 503
    assert captured.value.detail == "OPENAI_API_KEY is not configured"
