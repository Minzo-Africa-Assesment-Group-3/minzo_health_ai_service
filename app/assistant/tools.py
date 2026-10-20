import json
from collections.abc import Awaitable, Sequence
from typing import Annotated, Any, Literal, Protocol

from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import Field, StringConstraints, ValidationError

from app.clients.express_api import ExpressApiError
from app.schemas.assistant import AssistantPrincipal, SendBusinessMessageAction

CatalogueSearch = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)
]
ServiceSearch = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)
]
CatalogueLimit = Annotated[int, Field(ge=1, le=20)]


class AssistantExpressApi(Protocol):
    async def get_business(self, business_slug: str) -> Any: ...

    async def search_businesses(self, **filters: Any) -> Any: ...

    async def get_business_reviews(self, business_id: str, *, page: int, page_size: int) -> Any: ...

    async def get_business_rating(self, business_id: str) -> Any: ...

    async def search_services(self, search: str, *, limit: int) -> Any: ...

    async def search_counties(self, search: str, *, limit: int) -> Any: ...

    async def search_cities(self, county_id: str, search: str, *, limit: int) -> Any: ...

def _tool_result(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if len(serialized) <= 30_000:
        return serialized
    return json.dumps(
        {"truncated": True, "content": serialized[:30_000]},
        ensure_ascii=False,
    )


async def _read(operation: Awaitable[Any]) -> str:
    try:
        return _tool_result(await operation)
    except ExpressApiError as exc:
        if exc.status_code in {400, 422}:
            raise ToolException(
                "Backend rejected these search arguments. Check the tool schema: catalogue "
                "searches require at least two non-space characters and city lookup needs a "
                "county ID. For a broad city/services question use search_business_directory "
                "without filters, then inspect the returned locations and services."
            ) from exc
        if exc.status_code == 404:
            raise ToolException(
                "This record was not found. Search the directory and use an ID or slug "
                "from its results; do not invent identifiers."
            ) from exc
        raise


def _validation_message(error: ValidationError) -> str:
    fields = ", ".join(".".join(map(str, issue["loc"])) for issue in error.errors())
    return (
        f"Invalid tool arguments in: {fields}. Follow the field constraints in the tool schema. "
        "For broad questions about available cities or services, call "
        "search_business_directory without filters and read the returned locations/services."
    )


def build_tools(
    api: AssistantExpressApi,
    principal: AssistantPrincipal,
    confirmed_action: SendBusinessMessageAction | None,
) -> Sequence[BaseTool]:
    """Expose only public read operations to the conversational assistant."""
    if confirmed_action is not None or principal.capabilities or principal.delegation_token:
        raise ValueError("The assistant is read-only; write actions are not supported.")

    @tool
    async def get_business_information(business_slug: str) -> str:
        """Get an approved Minzo business's public profile by its URL slug."""
        return await _read(api.get_business(business_slug))

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
        """Search businesses by text, service, location or proximity.

        All filters are optional. For broad questions about which cities have services,
        call without filters and inspect location.cityOrTown and services in the results.
        Results are paginated examples, not a complete list of every city.
        """
        return await _read(
            api.search_businesses(
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
        return await _read(
            api.get_business_reviews(business_id, page=page, page_size=page_size)
        )

    @tool
    async def get_business_rating(business_id: str) -> str:
        """Get the current aggregate rating and review count for a business."""
        return await _read(api.get_business_rating(business_id))

    @tool
    async def search_service_catalogue(search: ServiceSearch, limit: CatalogueLimit = 10) -> str:
        """Find services matching at least two search characters; this is not a list-all tool."""
        return await _read(api.search_services(search.strip(), limit=limit))

    @tool
    async def search_county_catalogue(search: CatalogueSearch, limit: CatalogueLimit = 10) -> str:
        """Find counties matching at least two search characters; this is not a list-all tool."""
        return await _read(api.search_counties(search.strip(), limit=limit))

    @tool
    async def search_city_catalogue(
        county_id: str, search: CatalogueSearch, limit: CatalogueLimit = 10
    ) -> str:
        """Find cities in a known county ID with at least two search characters.

        This searches a county's city catalogue, not businesses offering a service.
        """
        return await _read(api.search_cities(county_id, search.strip(), limit=limit))

    tools: list[BaseTool] = [
        get_business_information,
        search_business_directory,
        get_business_reviews,
        get_business_rating,
        search_service_catalogue,
        search_county_catalogue,
        search_city_catalogue,
    ]

    for read_tool in tools:
        read_tool.handle_validation_error = _validation_message
        read_tool.handle_tool_error = True

    return tools
