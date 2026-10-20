from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import SecretStr

from app.clients.express_api import ExpressApiError


class CurrentUserApiClient:
    """Request-scoped client. Identity is derived by Backend from the bearer token."""

    def __init__(self, http: httpx.AsyncClient, token: SecretStr) -> None:
        self._http = http
        self._token = token

    async def _get(self, path: str, params: dict[str, int] | None = None) -> Any:
        try:
            response = await self._http.get(
                path,
                headers={
                    "Authorization": f"Bearer {self._token.get_secret_value()}",
                    "Accept": "application/json",
                },
                params=params,
                follow_redirects=False,
            )
            if response.status_code in {401, 403}:
                raise HTTPException(
                    status_code=response.status_code,
                    detail={
                        "code": "user_authentication_failed",
                        "message": "Please sign in again to access your account information.",
                    },
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ExpressApiError(f"GET {path}", exc.response.status_code) from None
        except (httpx.HTTPError, ValueError):
            raise ExpressApiError(f"GET {path}") from None

    async def get_profile(self) -> Any:
        return await self._get("/api/v1/me")

    async def get_reviews(self, *, page_number: int = 1, page_size: int = 10) -> Any:
        return await self._get(
            "/api/v1/me/reviews", {"pageNumber": page_number, "pageSize": page_size}
        )
