import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.api.dependencies import get_chat_model
from app.assistant.current_user_tools import build_current_user_tools
from app.assistant.service import AssistantService
from app.bootstrap import create_app
from app.clients.current_user_api import CurrentUserApiClient
from app.clients.express_api import ExpressApiClient
from app.core.config import Settings, get_settings
from app.schemas.assistant import AssistantRequest


async def test_personal_tool_schema_never_contains_token_or_identity_arguments():
    calls = []

    def backend(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [], "pagination": {"totalItems": 0}})

    async with httpx.AsyncClient(
        base_url="http://backend.test", transport=httpx.MockTransport(backend)
    ) as http:
        tools = build_current_user_tools(CurrentUserApiClient(http, SecretStr("private-token")))
        for tool in tools:
            schema = tool.get_input_schema().model_json_schema()
            assert "private-token" not in json.dumps(schema)
            assert not ({"user_id", "token", "access_token"} & schema.get("properties", {}).keys())
        profile = next(t for t in tools if t.name == "get_my_profile")
        reviews = next(t for t in tools if t.name == "get_my_reviews")
        await profile.ainvoke({})
        await reviews.ainvoke({"page_number": 2, "page_size": 5})

    assert calls[0].url.path == "/api/v1/me"
    assert calls[1].url.path == "/api/v1/me/reviews"
    assert dict(calls[1].url.params) == {"pageNumber": "2", "pageSize": "5"}
    assert all(r.headers["Authorization"] == "Bearer private-token" for r in calls)
    assert all("x-service-key" not in r.headers for r in calls)


async def test_concurrent_users_do_not_share_credentials():
    calls = []

    async def backend(request):
        await asyncio.sleep(0)
        calls.append(request)
        return httpx.Response(200, json={"displayName": "Test"})

    async with httpx.AsyncClient(
        base_url="http://backend.test", transport=httpx.MockTransport(backend)
    ) as http:
        api = ExpressApiClient(http, None)
        await asyncio.gather(
            api.for_user(SecretStr("user-a")).get_profile(),
            api.for_user(SecretStr("user-b")).get_profile(),
        )
        await api.search_businesses()
    assert {r.headers["Authorization"] for r in calls[:2]} == {"Bearer user-a", "Bearer user-b"}
    assert "authorization" not in calls[2].headers


@pytest.mark.parametrize("status", [401, 403])
async def test_user_client_propagates_invalid_or_unavailable_account(status):
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(status)),
    ) as http:
        api = CurrentUserApiClient(http, SecretStr("expired-token"))
        with pytest.raises(HTTPException) as exc:
            await api.get_reviews()
    assert exc.value.status_code == status
    assert exc.value.detail["code"] == "user_authentication_failed"
    assert "expired-token" not in str(exc.value)


def test_personal_tools_only_enabled_by_verified_client_not_body_user_id(monkeypatch):
    captured = []

    def capture_agent(**kwargs):
        captured.append(kwargs)
        return object()

    monkeypatch.setattr("app.assistant.service.create_agent", capture_agent)
    request = AssistantRequest(message="My reviews", principal={"user_id": "invented-user"})
    http = httpx.AsyncClient(base_url="http://backend.test")
    api = ExpressApiClient(http, None)
    anonymous = AssistantService(object(), api)
    anonymous._create_agent_run(request)
    assert not any(t.name.startswith("get_my_") for t in captured[0]["tools"])
    signed_in = AssistantService(
        object(), api, current_user_api=api.for_user(SecretStr("private-token"))
    )
    signed_in._create_agent_run(request)
    assert {t.name for t in captured[1]["tools"]} >= {"get_my_profile", "get_my_reviews"}
    assert "private-token" not in captured[1]["system_prompt"]
    assert "invented-user" not in captured[1]["system_prompt"]


@pytest.mark.parametrize("header", ["Basic invalid", "Bearer invalid", "Bearer one two"])
async def test_http_rejects_bad_user_identity_before_agent_runs(header):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, service_api_key="test-key"
    )
    app.dependency_overrides[get_chat_model] = lambda: object()
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(401)),
    ) as http:
        app.state.express_api = ExpressApiClient(http, None)
        async with httpx.AsyncClient(
            base_url="http://ai.test", transport=httpx.ASGITransport(app)
        ) as client:
            result = await client.post(
                "/v1/assistant/messages",
                headers={"X-Service-Key": "test-key", "Authorization": header},
                json={"message": "My profile"},
            )
    assert result.status_code == 401
    assert result.json()["detail"]["code"] == "user_authentication_failed"
