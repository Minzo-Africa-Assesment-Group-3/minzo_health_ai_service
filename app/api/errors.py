from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.clients.express_api import ExpressApiError
from app.clients.moderation_api import ModerationCallbackError


async def express_api_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    backend_status = exc.status_code if isinstance(exc, ExpressApiError) else None
    messages = {
        400: "Backend rejected the assistant's request arguments.",
        401: "Backend did not accept the service credentials.",
        403: "Backend did not allow this operation.",
        404: "The requested Backend record or endpoint was not found.",
        422: "Backend rejected the assistant's request arguments.",
        429: "Backend is receiving too many requests. Please try again shortly.",
    }
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": messages.get(backend_status, "The Minzo backend is temporarily unavailable"),
            "backendStatus": backend_status,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ExpressApiError, express_api_error_handler)
    app.add_exception_handler(ModerationCallbackError, moderation_callback_error_handler)


async def moderation_callback_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ModerationCallbackError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": str(exc), "callbackStatus": "NOT_CONFIRMED"},
    )
