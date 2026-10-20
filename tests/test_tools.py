import json

import pytest
from pydantic import SecretStr

from app.assistant.tools import build_tools
from app.clients.express_api import ExpressApiError
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
async def test_write_tool_is_unavailable_even_with_delegation() -> None:
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
    with pytest.raises(ValueError, match="read-only"):
        build_tools(api, principal, action)
    assert api.sent_message is None


@pytest.mark.parametrize("search", ["", " ", "a", " a "])
async def test_empty_or_short_catalogue_search_returns_corrective_tool_feedback(search):
    class NoCallApi(FakeExpressApi):
        async def search_counties(self, search, *, limit):
            pytest.fail("Invalid search must not reach Backend")

    tools = build_tools(NoCallApi(), AssistantPrincipal(), None)
    lookup = next(t for t in tools if t.name == "search_county_catalogue")
    result = await lookup.ainvoke({"search": search})
    assert "Invalid tool arguments" in result
    assert "search_business_directory" in result


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_backend_argument_errors_are_recoverable_tool_results(status):
    class RejectedApi(FakeExpressApi):
        async def search_businesses(self, **filters):
            raise ExpressApiError("GET /api/v1/businesses", status)

    tools = build_tools(RejectedApi(), AssistantPrincipal(), None)
    search = next(t for t in tools if t.name == "search_business_directory")
    result = await search.ainvoke({})
    assert "temporarily unavailable" not in result
    assert "rejected" in result or "not found" in result


async def test_real_backend_failure_is_not_misrepresented_as_empty_results():
    class FailedApi(FakeExpressApi):
        async def search_businesses(self, **filters):
            raise ExpressApiError("GET /api/v1/businesses", 503)

    tools = build_tools(FailedApi(), AssistantPrincipal(), None)
    search = next(t for t in tools if t.name == "search_business_directory")
    with pytest.raises(ExpressApiError):
        await search.ainvoke({})


async def test_general_discovery_can_be_called_without_search_text():
    tools = build_tools(FakeExpressApi(), AssistantPrincipal(), None)
    search = next(t for t in tools if t.name == "search_business_directory")
    result = json.loads(await search.ainvoke({}))
    assert result["search"] is None
    assert result["city"] is None
