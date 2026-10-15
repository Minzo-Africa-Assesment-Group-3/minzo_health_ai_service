from fastapi import APIRouter, Depends

from app.api.routes import assistant, health, moderation
from app.core.security import require_service_key

root_router = APIRouter()
root_router.include_router(health.router)

protected_router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_service_key)],
)
protected_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
protected_router.include_router(moderation.router, prefix="/moderation", tags=["moderation"])

root_router.include_router(protected_router)
