import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

service_key_header = APIKeyHeader(name="X-Service-Key", auto_error=False)


async def require_service_key(
    supplied_key: Annotated[str | None, Depends(service_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    configured = settings.service_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SERVICE_API_KEY is not configured",
        )

    expected = configured.get_secret_value()
    if not supplied_key or not secrets.compare_digest(supplied_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials",
        )
