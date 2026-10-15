from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.router import root_router
from app.clients.express_api import ExpressApiClient
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.express_api_base_url.rstrip("/"),
        timeout=settings.express_request_timeout_seconds,
    ) as http_client:
        token = (
            settings.express_service_token.get_secret_value()
            if settings.express_service_token
            else None
        )
        app.state.express_api = ExpressApiClient(http_client, token)
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Minzo Express AI",
        version="0.1.0",
        description=(
            "Internal LangChain assistant and review-moderation service for Minzo Africa. "
            "Protected endpoints require the service API key through `X-Service-Key`."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(root_router)
    return app
