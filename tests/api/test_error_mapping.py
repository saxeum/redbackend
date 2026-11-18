"""The controller owns status codes and wording: one entry per error code."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.api.errors import (
    UNAVAILABLE_ERRORS,
    error_response,
    register_exception_handlers,
)
from app.api.messages import MESSAGES
from app.domain.errors import Conflict, DomainError, ErrorCode
from app.main import app


def test_every_error_code_has_a_message() -> None:
    assert set(MESSAGES) == set(ErrorCode)


def test_messages_map_to_client_statuses() -> None:
    for code, spec in MESSAGES.items():
        assert 400 <= spec.status_code < 500, f"{code} -> {spec.status_code}"
        assert spec.message, f"{code} has no message"


def test_error_response_uses_the_table() -> None:
    response = error_response(Conflict(ErrorCode.EMAIL_TAKEN))

    assert response.status_code == 409
    assert json.loads(bytes(response.body)) == {
        "detail": "User with this email already exists"
    }


def test_error_response_can_override_the_status() -> None:
    response = error_response(Conflict(ErrorCode.EMAIL_TAKEN), status_code=400)

    assert response.status_code == 400


def test_domain_error_handler_is_registered() -> None:
    assert DomainError in app.exception_handlers
    for unavailable in UNAVAILABLE_ERRORS:
        assert unavailable in app.exception_handlers


@pytest.mark.parametrize(
    "unavailable",
    [OperationalError("database is down"), PoolTimeout("pool exhausted")],
    ids=["operational-error", "pool-timeout"],
)
def test_unavailable_errors_return_503(unavailable: Exception) -> None:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/boom")
    def boom() -> None:
        raise unavailable

    response = TestClient(test_app).get("/boom")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}
