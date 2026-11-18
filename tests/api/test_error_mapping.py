"""The controller owns status codes and wording: one entry per error code."""

import json

from app.api.errors import UNAVAILABLE_ERRORS, error_response
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
