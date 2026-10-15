from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.clients.express_api import ExpressApiError


async def express_api_error_handler(
    _request: Request,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "The Minzo backend is temporarily unavailable"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ExpressApiError, express_api_error_handler)
