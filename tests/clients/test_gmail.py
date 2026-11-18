"""Gmail adapter: wire format -> domain, cursor handling, client wiring.

No network: the discovery service is replaced with a fake chain that records
calls and returns canned payloads.
"""

import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from app.clients import gmail
from app.core.config import settings
from app.domain.errors import ErrorCode, InvalidOperation

CREDENTIALS = cast(Credentials, object())


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


RAW = {
    "id": "msg-1",
    "threadId": "thread-1",
    "internalDate": "1700000000000",
    "snippet": "the snippet",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Alice <alice@example.com>"},
            {"name": "Subject", "value": "Hello there"},
            {"name": "Date", "value": "Tue, 14 Nov 2023 22:13:20 +0000"},
        ],
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("plain body")}},
        ],
    },
}


class _Request:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def execute(self) -> Any:
        # Real clients fail during execute (token refresh, HTTP status), not
        # while building the request, so the fake does the same.
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Messages:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list(self, **kwargs: Any) -> _Request:
        self.calls.append(("list", kwargs))
        return _Request(self.payloads["list"])

    def get(self, **kwargs: Any) -> _Request:
        self.calls.append(("get", kwargs))
        return _Request(self.payloads["get"][kwargs["id"]])


class _History:
    """Pages are keyed by the page token that requests them ("0" is first)."""

    def __init__(self, pages: dict[str, Any]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> _Request:
        self.calls.append(kwargs)
        return _Request(self.pages[str(kwargs.get("pageToken", "0"))])


class _Users:
    def __init__(self, messages: _Messages, history: _History) -> None:
        self._messages = messages
        self._history = history

    def getProfile(self, **kwargs: Any) -> _Request:
        return _Request({"emailAddress": "inbox@example.com", "historyId": "900"})

    def messages(self) -> _Messages:
        return self._messages

    def history(self) -> _History:
        return self._history


def _not_found() -> HttpError:
    return HttpError(httplib2.Response({"status": 404}), b"not found")


@pytest.fixture
def api(monkeypatch: Any) -> dict[str, Any]:
    """Replace the discovery service with a fake Gmail API."""
    messages = _Messages(
        {
            "list": {"messages": [{"id": "msg-1"}, {"id": "msg-2"}]},
            "get": {"msg-1": RAW, "msg-2": RAW},
        }
    )
    history = _History({"0": {"history": [], "historyId": "900"}})
    users = _Users(messages, history)
    monkeypatch.setattr(
        gmail, "_service", lambda credentials: SimpleNamespace(users=lambda: users)
    )
    return {"messages": messages, "history": history}


def test_build_client_requires_configuration(monkeypatch: Any) -> None:
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.setattr(settings, name, None)

    with pytest.raises(InvalidOperation) as exc:
        gmail.build_client()

    assert exc.value.code is ErrorCode.MAIL_NOT_CONFIGURED


def test_build_client_uses_the_mail_credentials(monkeypatch: Any, api: Any) -> None:
    monkeypatch.setattr(settings, "GMAIL_CLIENT_ID", "mail-client")
    monkeypatch.setattr(settings, "GMAIL_CLIENT_SECRET", "mail-secret")
    monkeypatch.setattr(settings, "GMAIL_REFRESH_TOKEN", "mail-refresh")

    profile = gmail.build_client().profile()

    assert profile.address == "inbox@example.com"
    assert profile.cursor == "900"


def test_list_recent_ids_asks_the_inbox_for_the_limit(api: Any) -> None:
    client = gmail.GmailClient(credentials=CREDENTIALS)

    assert client.list_recent_ids(limit=2) == ["msg-1", "msg-2"]
    assert api["messages"].calls == [
        ("list", {"userId": "me", "q": gmail.INBOX_QUERY, "maxResults": 2})
    ]


def test_changes_since_asks_for_the_delta(api: Any) -> None:
    api["history"].pages["0"] = {
        "history": [
            {"messagesAdded": [{"message": {"id": "msg-1"}}]},
            {"messagesAdded": [{"message": {"id": "msg-2"}}]},
        ],
        "historyId": "950",
    }

    changes = gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="900")

    assert changes.added == ("msg-1", "msg-2")
    assert changes.cursor == "950"
    assert api["history"].calls == [
        {"userId": "me", "startHistoryId": "900", "maxResults": gmail.HISTORY_PAGE_SIZE}
    ]


def test_changes_since_follows_pages(api: Any) -> None:
    api["history"].pages = {
        "0": {
            "history": [{"messagesAdded": [{"message": {"id": "msg-1"}}]}],
            "historyId": "920",
            "nextPageToken": "1",
        },
        "1": {
            "history": [{"messagesAdded": [{"message": {"id": "msg-2"}}]}],
            "historyId": "950",
        },
    }

    changes = gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="900")

    assert changes.added == ("msg-1", "msg-2")
    assert changes.cursor == "950"
    assert len(api["history"].calls) == 2
    assert api["history"].calls[1]["pageToken"] == "1"


def test_changes_since_deduplicates_ids(api: Any) -> None:
    api["history"].pages["0"] = {
        "history": [
            {"messagesAdded": [{"message": {"id": "msg-1"}}]},
            {"messagesAdded": [{"message": {"id": "msg-1"}}]},
        ],
        "historyId": "950",
    }

    assert gmail.GmailClient(credentials=CREDENTIALS).changes_since(
        since="900"
    ).added == ("msg-1",)


def test_changes_since_reports_an_expired_cursor(api: Any) -> None:
    api["history"].pages["0"] = _not_found()

    with pytest.raises(gmail.HistoryExpired):
        gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="1")


def test_changes_since_propagates_other_http_errors(api: Any) -> None:
    api["history"].pages["0"] = HttpError(httplib2.Response({"status": 500}), b"boom")

    with pytest.raises(HttpError):
        gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="1")


def test_revoked_credentials_surface_as_mail_auth_error(api: Any) -> None:
    api["history"].pages["0"] = RefreshError("invalid_grant")

    with pytest.raises(gmail.MailAuthError):
        gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="1")


def test_rejected_requests_surface_as_mail_auth_error(api: Any) -> None:
    api["history"].pages["0"] = HttpError(
        httplib2.Response({"status": 401}), b"unauthorized"
    )

    with pytest.raises(gmail.MailAuthError):
        gmail.GmailClient(credentials=CREDENTIALS).changes_since(since="1")


def test_fetch_asks_for_the_full_message(api: Any) -> None:
    client = gmail.GmailClient(credentials=CREDENTIALS)

    fetched = client.fetch(remote_id="msg-1")

    assert fetched.remote_id == "msg-1"
    assert api["messages"].calls == [
        ("get", {"userId": "me", "id": "msg-1", "format": "full"})
    ]


def test_to_fetched_mail_maps_the_wire_format() -> None:
    mail = gmail.to_fetched_mail(RAW)

    assert mail.remote_id == "msg-1"
    assert mail.thread_id == "thread-1"
    assert mail.from_address == "Alice <alice@example.com>"
    assert mail.subject == "Hello there"
    assert mail.snippet == "the snippet"
    assert mail.body == "plain body"
    assert mail.received_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_to_fetched_mail_falls_back_to_the_snippet() -> None:
    raw = {
        "id": "msg-2",
        "threadId": "thread-2",
        "internalDate": "1700000000000",
        "snippet": "only a snippet",
        "payload": {"mimeType": "text/html", "headers": [], "body": {}},
    }

    mail = gmail.to_fetched_mail(raw)

    assert mail.body == "only a snippet"
    assert mail.subject is None
    assert mail.from_address == ""


def test_received_at_falls_back_to_the_date_header() -> None:
    raw = {
        "id": "msg-3",
        "threadId": "thread-3",
        "payload": {
            "headers": [{"name": "Date", "value": "Tue, 14 Nov 2023 22:13:20 +0000"}]
        },
    }

    mail = gmail.to_fetched_mail(raw)

    assert mail.received_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_received_at_falls_back_to_now_when_nothing_parses() -> None:
    raw = {
        "id": "msg-4",
        "threadId": "thread-4",
        "payload": {"headers": [{"name": "Date", "value": "not a date"}]},
    }

    mail = gmail.to_fetched_mail(raw)

    assert abs((mail.received_at - datetime.now(UTC)).total_seconds()) < 5
