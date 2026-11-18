"""Mail controller tests: the service layer is mocked; HTTP concerns are real."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.core.config import settings
from app.domain.errors import ErrorCode, NotFound
from app.domain.mail import PollResult
from app.domain.models import User
from tests.fakes import make_mail, make_user

API = "/api/v1"


def detail(code: ErrorCode) -> str:
    return MESSAGES[code].message


def test_poll_returns_the_cycle_counts(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=True))
    captured: dict[str, Any] = {}

    def fake_build() -> Any:
        captured["client_built"] = True
        return object()

    def fake_poll(*, conn: Any, client: Any, limit: int) -> PollResult:
        captured["limit"] = limit
        return PollResult(
            mailbox="inbox@example.com",
            mode="incremental",
            listed=3,
            stored=2,
            skipped=1,
            cursor="950",
        )

    monkeypatch.setattr("app.api.routes.mail.gmail.build_client", fake_build)
    monkeypatch.setattr("app.services.mailbox.poll_new", fake_poll)

    response = client.post(f"{API}/mail/poll?limit=5")

    assert response.status_code == 200
    assert response.json() == {
        "mailbox": "inbox@example.com",
        "mode": "incremental",
        "listed": 3,
        "stored": 2,
        "skipped": 1,
        "cursor": "950",
    }
    assert captured == {"client_built": True, "limit": 5}


def test_poll_is_superuser_only(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=False))

    def never_build() -> Any:
        raise AssertionError("the client must not be built for a denied request")

    monkeypatch.setattr("app.api.routes.mail.gmail.build_client", never_build)

    response = client.post(f"{API}/mail/poll")

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.INSUFFICIENT_PRIVILEGES)


def test_poll_without_configuration_is_404(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=True))
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.setattr(settings, name, None)

    response = client.post(f"{API}/mail/poll")

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.MAIL_NOT_CONFIGURED)


def test_list_mail_returns_a_page(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=True))
    mail = make_mail(subject="Invoice", snippet="please pay")
    monkeypatch.setattr(
        "app.services.mailbox.list_messages",
        lambda *, conn, actor, skip, limit: ([mail], 1),
    )

    body = client.get(f"{API}/mail/messages").json()

    assert body["count"] == 1
    assert body["data"][0]["subject"] == "Invoice"
    assert "body" not in body["data"][0]


def test_list_mail_is_superuser_only(
    client: TestClient, as_user: Callable[[User], None]
) -> None:
    as_user(make_user(is_superuser=False))

    response = client.get(f"{API}/mail/messages")

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.INSUFFICIENT_PRIVILEGES)


def test_read_mail_returns_the_body(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=True))
    mail = make_mail(subject="Invoice")
    monkeypatch.setattr(
        "app.services.mailbox.get_message", lambda *, conn, actor, mail_id: mail
    )

    body = client.get(f"{API}/mail/messages/{mail.id}").json()

    assert body["subject"] == "Invoice"
    assert body["body"] == mail.body


def test_read_unknown_mail_is_404(
    client: TestClient, as_user: Callable[[User], None], monkeypatch: Any
) -> None:
    as_user(make_user(is_superuser=True))

    def fake_get(*, conn: Any, actor: Any, mail_id: uuid.UUID) -> Any:
        raise NotFound(ErrorCode.MAIL_NOT_FOUND)

    monkeypatch.setattr("app.services.mailbox.get_message", fake_get)

    response = client.get(f"{API}/mail/messages/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.MAIL_NOT_FOUND)
