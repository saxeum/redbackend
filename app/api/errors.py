"""Domain errors -> HTTP responses, in one place."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.domain.errors import (
    Conflict,
    DomainError,
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    InvalidOperation,
    NotFound,
    PermissionDenied,
)

# Ordered by specificity: subclasses before their base classes.
_MAPPING: tuple[tuple[type[DomainError], int], ...] = (
    (NotFound, 404),
    (PermissionDenied, 403),
    (EmailAlreadyRegistered, 400),
    (Conflict, 409),
    (InvalidCredentials, 400),
    (InactiveUser, 400),
    (InvalidOperation, 400),
)


def _handler(status_code: int) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handle(_: Request, exc: Exception) -> Response:
        detail = exc.message if isinstance(exc, DomainError) else str(exc)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    return handle


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status_code in _MAPPING:
        app.add_exception_handler(exc_type, _handler(status_code))
