from contextlib import asynccontextmanager
from uuid import UUID

import httpx
import pytest

from app.api.dependencies import get_moderation_callback, get_review_moderator
from app.bootstrap import create_app
from app.clients.moderation_api import ModerationApiClient
from app.core.config import Settings, get_settings
from app.review_moderation.service import ReviewModerator
from app.schemas.moderation import ReviewModerationDecision

KEY = "i" * 64
CALLBACK_KEY = "c" * 64
REVIEW_ID = "9b2c7aaa-fb70-438c-a863-a31634985683"
ACTION_ID = "479247ab-6aab-4af8-b9a9-e170e7e24d31"
PATH = "/v1/moderation/customer-reviews/evaluate"
BODY = {
    "reviewId": REVIEW_ID,
    "reviewUpdatedAt": "2026-10-19T10:30:00.000Z",
    "text": "The waiting time was too long.",
    "stars": 2,
    "business": {
        "id": "9dc967aa-d458-4a52-a06f-dc1e29598148",
        "name": "Example Medical Center",
    },
}


class FakeModel:
    def __init__(self, decision):
        self.decision = ReviewModerationDecision.model_validate(decision)
        self.calls = []

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.decision


def model_decision(**overrides):
    return {
        "is_abusive": False,
        "action": "allow",
        "categories": ["none"],
        "severity": "none",
        "confidence": 0.99,
        "explanation": "Ordinary criticism of the service.",
        "requires_human_review": False,
        **overrides,
    }


def recorded(decision="APPROVED"):
    return {
        "reviewId": REVIEW_ID,
        "publicationStatus": "HIDDEN" if decision == "REJECTED" else "PUBLISHED",
        "moderationStatus": decision,
        "moderation": {
            "id": ACTION_ID,
            "actorType": "AUTOMATION",
            "decision": decision,
            "adminUserId": None,
            "actorReference": "langchain-review-moderator-v1",
            "reason": "Ordinary criticism of the service.",
            "createdAt": "2026-10-19T10:31:00.000Z",
            "moderatedBy": "AI",
        },
    }


@asynccontextmanager
async def api(handler, *, decision=None, callback_key=CALLBACK_KEY):
    model = FakeModel(decision or model_decision())
    moderator = ReviewModerator(
        model,
        model_name="fake-test-model",
        policy_version="test",
        flag_confidence_threshold=0.85,
        block_confidence_threshold=0.95,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, service_api_key=KEY
    )
    app.dependency_overrides[get_review_moderator] = lambda: moderator
    async with httpx.AsyncClient(
        base_url="http://backend.test", transport=httpx.MockTransport(handler)
    ) as backend:
        callback = ModerationApiClient(backend, callback_key)
        app.dependency_overrides[get_moderation_callback] = lambda: callback
        async with httpx.AsyncClient(
            base_url="http://ai.test", transport=httpx.ASGITransport(app=app)
        ) as client:
            yield client, model


@pytest.mark.parametrize("key", [None, "wrong-key"])
async def test_evaluation_requires_service_authentication(key):
    def no_callback(_request):
        pytest.fail("Unauthenticated request must not reach Backend")

    async with api(no_callback) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": key} if key else {})
    assert response.status_code == 401
    assert model.calls == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "APPROVED"),
        ({"confidence": 0.4}, "FLAGGED"),
        ({"requires_human_review": True}, "FLAGGED"),
        ({"explanation": " "}, "FLAGGED"),
        ({"action": "block", "categories": ["threat"], "severity": "high"}, "REJECTED"),
    ],
)
async def test_evaluates_then_records_decision(overrides, expected):
    calls = []

    def callback(request):
        calls.append(request)
        return httpx.Response(200, json=recorded(expected))

    async with api(callback, decision=model_decision(**overrides)) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})

    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == expected
    assert result["callbackStatus"] == "RECORDED"
    assert result["moderatedBy"] == "AI"
    assert result["moderationId"] == ACTION_ID
    assert result["reviewUpdatedAt"] == BODY["reviewUpdatedAt"]
    assert len(model.calls) == 1
    assert "Example Medical Center" in model.calls[0][1].content
    assert len(calls) == 1
    assert calls[0].method == "PATCH"
    assert calls[0].url.path == f"/api/v1/automation/customer-reviews/{REVIEW_ID}/moderation"
    assert calls[0].headers["X-Service-Key"] == CALLBACK_KEY
    assert "authorization" not in calls[0].headers
    import json

    assert json.loads(calls[0].content) == {
        "decision": expected,
        "reason": result["reason"],
        "reviewUpdatedAt": BODY["reviewUpdatedAt"],
    }


@pytest.mark.parametrize("status", [404, 409, 401, 400])
async def test_terminal_callback_errors_do_not_retry_or_claim_success(status):
    calls = []

    def callback(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "Backend rejected request"})

    async with api(callback) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})
    assert response.status_code == (status if status in {404, 409} else 502)
    assert response.json()["callbackStatus"] == "NOT_CONFIRMED"
    assert len(calls) == 1
    assert len(model.calls) == 1


async def test_retries_callback_without_rerunning_model():
    calls = []

    def callback(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=recorded())

    async with api(callback) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})
    assert response.status_code == 200
    assert len(calls) == 2
    assert len(model.calls) == 1


async def test_callback_transport_failure_has_bounded_retries():
    calls = []

    def callback(request):
        calls.append(request)
        raise httpx.ConnectError("Cannot connect", request=request)

    async with api(callback) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})
    assert response.status_code == 502
    assert response.json()["callbackStatus"] == "NOT_CONFIRMED"
    assert len(calls) == 3
    assert len(model.calls) == 1


async def test_missing_callback_key_is_reported_before_model_call():
    async with api(lambda _: httpx.Response(500), callback_key=None) as (client, model):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})
    assert response.status_code == 503
    assert model.calls == []


@pytest.mark.parametrize(
    "updates",
    [
        {"reviewId": "invalid-id"},
        {"reviewUpdatedAt": "2026-10-19"},
        {"reviewUpdatedAt": "2026-99-19T10:30:00.000Z"},
        {"stars": 6},
        {"text": "   "},
        {"callbackUrl": "https://untrusted.example"},
    ],
)
async def test_invalid_review_rejected_before_model_or_callback(updates):
    async with api(lambda _: httpx.Response(500)) as (client, model):
        response = await client.post(PATH, json={**BODY, **updates}, headers={"X-Service-Key": KEY})
    assert response.status_code == 422
    assert model.calls == []


async def test_invalid_backend_confirmation_is_not_success():
    bad = recorded()
    bad["reviewId"] = str(UUID(int=1))
    async with api(lambda _: httpx.Response(200, json=bad)) as (client, _):
        response = await client.post(PATH, json=BODY, headers={"X-Service-Key": KEY})
    assert response.status_code == 502
    assert response.json()["code"] == "invalid_callback_response"


async def test_legacy_analysis_route_still_has_no_callback():
    def no_callback(_request):
        pytest.fail("Analysis-only route must not write to Backend")

    async with api(no_callback) as (client, _):
        response = await client.post(
            "/v1/moderation/reviews",
            json={"review_id": REVIEW_ID, "text": BODY["text"]},
            headers={"X-Service-Key": KEY},
        )
    assert response.status_code == 200
    assert response.json()["decision"]["action"] == "allow"


async def test_assistant_refuses_write_capabilities_at_http_boundary():
    # Override model dependency so the test never needs an OpenAI key.
    from app.api.dependencies import get_chat_model

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, service_api_key=KEY)
    app.dependency_overrides[get_chat_model] = lambda: object()
    # Assistant dependency needs this attribute, but the invalid body prevents execution.
    app.state.express_api = object()
    async with httpx.AsyncClient(
        base_url="http://ai.test", transport=httpx.ASGITransport(app=app)
    ) as client:
        response = await client.post(
            "/v1/assistant/messages",
            headers={"X-Service-Key": KEY},
            json={
                "message": "Send this message",
                "principal": {
                    "user_id": "user-1",
                    "capabilities": ["send_business_message"],
                    "delegation_token": "test-token",
                },
            },
        )
    assert response.status_code == 422
