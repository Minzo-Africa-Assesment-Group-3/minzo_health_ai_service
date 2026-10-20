import logging
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class ExpressApiError(RuntimeError):
    """Raised when the deterministic backend cannot complete a tool action."""

    def __init__(self, operation: str, status_code: int | None = None) -> None:
        super().__init__(operation)
        self.operation = operation
        self.status_code = status_code


class ExpressApiClient:
    """Narrow adapter around Minzo's Express API.

    Update route paths here when the real Express contracts are available. Keeping
    them in one adapter prevents LangChain tools from depending on transport details.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        service_token: str | None,
    ) -> None:
        self._client = client
        self._service_token = service_token

    def for_user(self, token: SecretStr):
        from app.clients.current_user_api import CurrentUserApiClient

        return CurrentUserApiClient(self._client, token)

    def _headers(
        self,
        *,
        bearer_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return {"ok": True}
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Backend request rejected: %s %s returned HTTP %s",
                method, path, exc.response.status_code,
            )
            raise ExpressApiError(f"{method} {path}", exc.response.status_code) from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Backend request failed: %s %s (%s)", method, path, type(exc).__name__)
            raise ExpressApiError(f"{method} {path}") from exc

    async def get_business(self, business_slug: str) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/businesses/{quote(business_slug, safe='')}",
            headers=self._headers(),
        )

    async def search_businesses(
        self,
        *,
        search: str | None = None,
        county: str | None = None,
        city: str | None = None,
        service_id: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float | None = None,
        sort: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Any:
        params: dict[str, str | int | float] = {
            "pageNumber": max(1, page),
            "pageSize": _bounded_limit(page_size, maximum=50),
        }
        optional_params = {
            "search": search,
            "county": county,
            "city": city,
            "serviceId": service_id,
            "latitude": latitude,
            "longitude": longitude,
            "radiusKm": radius_km,
            "sort": sort,
        }
        params.update({key: value for key, value in optional_params.items() if value is not None})
        return await self._request(
            "GET",
            "/api/v1/businesses",
            params=params,
            headers=self._headers(),
        )

    async def get_business_reviews(
        self, business_id: str, *, page: int = 1, page_size: int = 10
    ) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/businesses/{quote(business_id, safe='')}/reviews",
            params={
                "pageNumber": max(1, page),
                "pageSize": _bounded_limit(page_size, maximum=50),
            },
            headers=self._headers(),
        )

    async def get_business_rating(self, business_id: str) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/businesses/{quote(business_id, safe='')}/rating",
            headers=self._headers(),
        )

    async def search_services(self, search: str, *, limit: int = 10) -> Any:
        return await self._request(
            "GET",
            "/api/v1/services",
            params={"search": search, "limit": _bounded_limit(limit, maximum=20)},
            headers=self._headers(),
        )

    async def search_counties(self, search: str, *, limit: int = 10) -> Any:
        return await self._request(
            "GET",
            "/api/v1/counties",
            params={"search": search, "limit": _bounded_limit(limit, maximum=20)},
            headers=self._headers(),
        )

    async def search_cities(self, county_id: str, search: str, *, limit: int = 10) -> Any:
        return await self._request(
            "GET",
            "/api/v1/cities",
            params={
                "countyId": county_id,
                "search": search,
                "limit": _bounded_limit(limit, maximum=20),
            },
            headers=self._headers(),
        )

    async def send_business_message(
        self,
        *,
        delegation_token: str,
        business_id: str,
        message: str,
        idempotency_key: str,
    ) -> Any:
        return await self._request(
            "POST",
            f"/api/v1/businesses/{business_id}/contact-messages",
            headers=self._headers(
                bearer_token=delegation_token,
                idempotency_key=idempotency_key,
            ),
            json={"message": message},
        )


def _bounded_limit(value: int, *, maximum: int) -> int:
    return min(max(1, value), maximum)
