import httpx
import pytest

from app.clients.express_api import ExpressApiClient


@pytest.mark.asyncio
async def test_search_businesses_uses_current_express_query_names() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(
        base_url="http://express.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        api = ExpressApiClient(http_client, service_token=None)
        await api.search_businesses(
            search="clinic",
            county="Montserrado",
            service_id="service-1",
            page=2,
            page_size=25,
        )

    assert captured_request is not None
    assert captured_request.url.path == "/api/v1/businesses"
    assert captured_request.url.params["search"] == "clinic"
    assert captured_request.url.params["county"] == "Montserrado"
    assert captured_request.url.params["serviceId"] == "service-1"
    assert captured_request.url.params["pageNumber"] == "2"
    assert "page" not in captured_request.url.params
    assert captured_request.url.params["pageSize"] == "25"


@pytest.mark.asyncio
async def test_reviews_pagination_and_public_request_has_no_credentials() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(
        base_url="http://express.test", transport=httpx.MockTransport(handler)
    ) as http_client:
        api = ExpressApiClient(http_client, service_token="must-not-leak")
        await api.get_business_reviews("business-1", page=3, page_size=10)

    assert calls[0].url.params["pageNumber"] == "3"
    assert "page" not in calls[0].url.params
    assert "authorization" not in calls[0].headers
    assert "x-service-key" not in calls[0].headers


@pytest.mark.asyncio
async def test_confirmed_message_uses_business_scoped_route_and_delegation() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(201, json={"id": "message-1"})

    async with httpx.AsyncClient(
        base_url="http://express.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        api = ExpressApiClient(http_client, service_token=None)
        await api.send_business_message(
            delegation_token="signed-delegation",
            business_id="business-1",
            message="Please call me.",
            idempotency_key="message-12345",
        )

    assert captured_request is not None
    assert captured_request.url.path == "/api/v1/businesses/business-1/contact-messages"
    assert captured_request.headers["Authorization"] == "Bearer signed-delegation"
    assert captured_request.headers["Idempotency-Key"] == "message-12345"
    assert captured_request.read() == b'{"message":"Please call me."}'
