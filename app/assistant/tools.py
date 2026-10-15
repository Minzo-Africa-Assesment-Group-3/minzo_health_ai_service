import json
from collections.abc import Sequence
from typing import Any, Literal, Protocol

from langchain_core.tools import BaseTool, tool

from app.schemas.assistant import AssistantPrincipal, SendBusinessMessageAction


class AssistantExpressApi(Protocol):
    async def get_business(self, business_slug: str) -> Any: ...

    async def search_businesses(self, **filters: Any) -> Any: ...

    async def get_business_reviews(self, business_id: str, *, page: int, page_size: int) -> Any: ...

    async def get_business_rating(self, business_id: str) -> Any: ...

    async def search_services(self, search: str, *, limit: int) -> Any: ...

    async def search_counties(self, search: str, *, limit: int) -> Any: ...

    async def search_cities(self, county_id: str, search: str, *, limit: int) -> Any: ...

    async def send_business_message(
        self,
        *,
        delegation_token: str,
        business_id: str,
        message: str,
        idempotency_key: str,
    ) -> Any: ...


def _tool_result(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if len(serialized) <= 30_000:
        return serialized
    return json.dumps(
        {"truncated": True, "content": serialized[:30_000]},
        ensure_ascii=False,
    )


def build_tools(
    api: AssistantExpressApi,
    principal: AssistantPrincipal,
    confirmed_action: SendBusinessMessageAction | None,
) -> Sequence[BaseTool]:
    """Create request-scoped tools with any mutation bound to a confirmed action.

    The model never chooses an acting user, delegation token, idempotency key, or
    mutation arguments.
    """

    @tool
    async def get_business_information(business_slug: str) -> str:
        """Get an approved Minzo business's public profile by its URL slug."""
        return _tool_result(await api.get_business(business_slug))

    @tool
    async def search_business_directory(
        search: str = "",
        county: str = "",
        city: str = "",
        service_id: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float | None = None,
        sort: Literal["name", "newest", "distance"] | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> str:
        """Search approved Minzo businesses by text, service, location, or proximity."""
        return _tool_result(
            await api.search_businesses(
                search=search or None,
                county=county or None,
                city=city or None,
                service_id=service_id or None,
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                sort=sort,
                page=page,
                page_size=page_size,
            )
        )

    @tool
    async def get_business_reviews(business_id: str, page: int = 1, page_size: int = 10) -> str:
        """Get public reviews for a business when review context is requested."""
        return _tool_result(
            await api.get_business_reviews(business_id, page=page, page_size=page_size)
        )

    @tool
    async def get_business_rating(business_id: str) -> str:
        """Get the current aggregate rating and review count for a business."""
        return _tool_result(await api.get_business_rating(business_id))

    @tool
    async def search_service_catalogue(search: str, limit: int = 10) -> str:
        """Find Minzo service catalogue entries for a user's requested service."""
        return _tool_result(await api.search_services(search, limit=limit))

    @tool
    async def search_county_catalogue(search: str, limit: int = 10) -> str:
        """Find supported Liberian counties for directory filtering."""
        return _tool_result(await api.search_counties(search, limit=limit))

    @tool
    async def search_city_catalogue(county_id: str, search: str, limit: int = 10) -> str:
        """Find supported cities or towns within a selected county."""
        return _tool_result(await api.search_cities(county_id, search, limit=limit))

    tools: list[BaseTool] = [
        get_business_information,
        search_business_directory,
        get_business_reviews,
        get_business_rating,
        search_service_catalogue,
        search_county_catalogue,
        search_city_catalogue,
    ]

    if confirmed_action is not None:
        delegation_token = principal.delegation_token
        if "send_business_message" not in principal.capabilities or delegation_token is None:
            raise ValueError("confirmed business message is not authorized")

        @tool
        async def send_confirmed_message_to_business() -> str:
            """Send the exact business message already confirmed by the user."""
            return _tool_result(
                await api.send_business_message(
                    delegation_token=delegation_token.get_secret_value(),
                    business_id=confirmed_action.business_id,
                    message=confirmed_action.message,
                    idempotency_key=confirmed_action.idempotency_key,
                )
            )

        tools.append(send_confirmed_message_to_business)

    return tools
