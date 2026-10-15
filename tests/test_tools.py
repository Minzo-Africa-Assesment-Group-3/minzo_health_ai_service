import json

import pytest
from pydantic import SecretStr

from app.assistant.tools import build_tools
from app.schemas.assistant import AssistantPrincipal, SendBusinessMessageAction


class FakeExpressApi:
    def __init__(self) -> None:
        self.sent_message: dict[str, str] | None = None

    async def get_business(self, business_slug: str):
        return {"slug": business_slug}

    async def search_businesses(self, **filters):
        return filters

    async def get_business_reviews(self, business_id: str, *, page: int, page_size: int):
        return {"businessId": business_id, "items": [], "page": page, "pageSize": page_size}

    async def get_business_rating(self, business_id: str):
        return {"businessId": business_id, "averageRating": 4.5}

    async def search_services(self, search: str, *, limit: int):
        return {"search": search, "limit": limit}

    async def search_counties(self, search: str, *, limit: int):
        return {"search": search, "limit": limit}

    async def search_cities(self, county_id: str, search: str, *, limit: int):
        return {"countyId": county_id, "search": search, "limit": limit}

    async def send_business_message(
        self,
        *,
        delegation_token: str,
        business_id: str,
        message: str,
        idempotency_key: str,
    ):
        self.sent_message = {
            "token": delegation_token,
            "businessId": business_id,
            "message": message,
            "idempotencyKey": idempotency_key,
        }
        return {"sent": True}


@pytest.mark.asyncio
async def test_business_profile_tool_uses_slug() -> None:
    api = FakeExpressApi()
    tools = build_tools(api, AssistantPrincipal(), None)
    business_tool = next(tool for tool in tools if tool.name == "get_business_information")

    result = json.loads(await business_tool.ainvoke({"business_slug": "test-clinic"}))

    assert result["slug"] == "test-clinic"


def test_write_tools_are_disabled_by_default() -> None:
    tools = build_tools(FakeExpressApi(), AssistantPrincipal(), None)
    names = {tool.name for tool in tools}
    assert "send_confirmed_message_to_business" not in names


@pytest.mark.asyncio
async def test_confirmed_message_tool_is_bound_to_exact_action() -> None:
    api = FakeExpressApi()
    principal = AssistantPrincipal(
        user_id="user-1",
        capabilities={"send_business_message"},
        delegation_token=SecretStr("delegation-token"),
    )
    action = SendBusinessMessageAction(
        business_id="business-1",
        message="Please call me.",
        idempotency_key="message-12345",
    )
    tools = build_tools(api, principal, action)
    send_tool = next(tool for tool in tools if tool.name == "send_confirmed_message_to_business")

    result = json.loads(await send_tool.ainvoke({}))

    assert result == {"sent": True}
    assert api.sent_message == {
        "token": "delegation-token",
        "businessId": "business-1",
        "message": "Please call me.",
        "idempotencyKey": "message-12345",
    }
