"""Domain errors -> HTTP responses. The controller owns status and wording.

Domain errors carry a code; this module looks the code up in
app/api/messages.py and decorates the response. Routes may catch a domain error
and call error_response() themselves when an endpoint needs to deviate from the
table (none currently do).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from app.api.messages import MESSAGES
from app.api.schemas import ErrorResponse
from app.domain.errors import DomainError, ErrorCode

logger = logging.getLogger(__name__)

# 503 is infrastructure, not a domain code, but every DB-backed route can emit it.
UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    503: {
        "model": ErrorResponse,
        "description": "Service temporarily unavailable",
    }
}


def error_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries generated from the controller message table."""
    grouped: dict[int, list[str]] = {}
    for code in codes:
        spec = MESSAGES[code]
        grouped.setdefault(spec.status_code, []).append(spec.message)
    return {
        status_code: {
            "model": ErrorResponse,
            "description": " / ".join(descriptions),
        }
        for status_code, descriptions in grouped.items()
    }


def api_responses(
    *codes: ErrorCode, auth: bool = True
) -> dict[int | str, dict[str, Any]]:
    """Responses for a route: its domain codes, bearer auth, and 503."""
    selected = (*codes, ErrorCode.INVALID_TOKEN) if auth else codes
    responses = error_responses(*selected)
    responses.update(UNAVAILABLE_RESPONSE)
    return responses


# Infrastructure failures are not domain failures: they are availability
# problems, so they map to 503 rather than pretending to be domain state.
UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    psycopg.OperationalError,
    PoolTimeout,
)


def error_response(exc: DomainError, *, status_code: int | None = None) -> JSONResponse:
    """Decorate a domain error as an HTTP response."""
    spec = MESSAGES[exc.code]
    return JSONResponse(
        status_code=status_code if status_code is not None else spec.status_code,
        content={"detail": spec.message},
    )


async def _domain_handler(_: Request, exc: Exception) -> Response:
    if not isinstance(exc, DomainError):
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
    spec = MESSAGES.get(exc.code)
    if spec is None:
        logger.error("unmapped domain error code: %s", exc.code)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
    return JSONResponse(status_code=spec.status_code, content={"detail": spec.message})


def _unavailable_handler() -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handle(request: Request, _exc: Exception) -> Response:
        logger.exception(
            "database unavailable on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=503, content={"detail": "Service temporarily unavailable"}
        )

    return handle


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_handler)
    for unavailable in UNAVAILABLE_ERRORS:
        app.add_exception_handler(unavailable, _unavailable_handler())
