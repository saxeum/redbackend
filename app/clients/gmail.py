"""Gmail adapter.

A *separate* OAuth client from sign-in: the mailbox polled here belongs to one
admin account, while sign-in authenticates ordinary users. Only a refresh token
is configured; the library mints access tokens per request.

This module is the only place that knows Gmail's wire format. `to_fetched_mail`
turns a raw API payload into a domain object, so nothing downstream depends on
Google's JSON shape.

Polling position is Gmail's `historyId`: `changes_since` asks for the delta
between a stored id and now, which is what makes a cycle both complete and
cheap. Gmail keeps that window for a limited time; an older cursor raises
`HistoryExpired` and the service falls back to a full sync.
"""

import base64
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Final, Protocol

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.domain.errors import ErrorCode, InvalidOperation
from app.domain.mail import FetchedMail, MailboxChanges, MailboxProfile

# Phase 1 only reads, but the token is minted with modify scope so later phases
# (labels, replies) do not need a new consent round.
SCOPES: Final = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_URI: Final = "https://oauth2.googleapis.com/token"
INBOX_QUERY: Final = "in:inbox"
# Gmail caps history pages; a big backlog can need several. Stop rather than
# spin forever, and let the next cycle continue from the last cursor returned.
HISTORY_PAGE_SIZE: Final = 500
HISTORY_MAX_PAGES: Final = 20


class HistoryExpired(Exception):
    """Gmail no longer holds history back to the stored cursor."""


class MailAuthError(Exception):
    """The mailbox credentials were rejected: revoked, expired or wrong client."""


def _execute(request: Any) -> Any:
    """Run a Google API request, translating credential failures.

    The access token is refreshed lazily on the first call, so a dead refresh
    token surfaces here rather than when the client is built.
    """
    try:
        return request.execute()
    except RefreshError as exc:
        raise MailAuthError(str(exc)) from exc
    except HttpError as exc:
        if getattr(exc.resp, "status", None) in (401, 403):
            raise MailAuthError(str(exc)) from exc
        raise


class MailClient(Protocol):
    """What the mailbox service needs from a mail provider."""

    def profile(self) -> MailboxProfile: ...

    def list_recent_ids(self, *, limit: int) -> list[str]: ...

    def changes_since(self, *, since: str) -> MailboxChanges: ...

    def fetch(self, *, remote_id: str) -> FetchedMail: ...


def is_configured() -> bool:
    return bool(
        settings.GMAIL_CLIENT_ID
        and settings.GMAIL_CLIENT_SECRET
        and settings.GMAIL_REFRESH_TOKEN
    )


def build_client() -> MailClient:
    if not is_configured():
        raise InvalidOperation(ErrorCode.MAIL_NOT_CONFIGURED)
    credentials = Credentials(  # pyright: ignore[reportUnknownMemberType]
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return GmailClient(credentials)


def _service(credentials: Credentials) -> Any:
    # Discovery is fetched once per client; the instance is short-lived (one
    # polling cycle), so this is cheaper than caching a non-thread-safe client.
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


class GmailClient:
    def __init__(self, credentials: Credentials) -> None:
        self._users: Any = _service(credentials).users()

    def profile(self) -> MailboxProfile:
        raw: Mapping[str, Any] = _execute(self._users.getProfile(userId="me"))
        return MailboxProfile(
            address=str(raw["emailAddress"]), cursor=str(raw["historyId"])
        )

    def list_recent_ids(self, *, limit: int) -> list[str]:
        response: Mapping[str, Any] = _execute(
            self._users.messages().list(userId="me", q=INBOX_QUERY, maxResults=limit)
        )
        messages: list[Mapping[str, Any]] = response.get("messages", [])
        return [str(message["id"]) for message in messages]

    def changes_since(self, *, since: str) -> MailboxChanges:
        added: list[str] = []
        cursor = since
        page_token: str | None = None

        for _ in range(HISTORY_MAX_PAGES):
            params: dict[str, Any] = {
                "userId": "me",
                "startHistoryId": since,
                "maxResults": HISTORY_PAGE_SIZE,
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                response: Mapping[str, Any] = _execute(
                    self._users.history().list(**params)
                )
            except HttpError as exc:
                # 404 means the cursor predates Gmail's retained history.
                if getattr(exc.resp, "status", None) == 404:
                    raise HistoryExpired(since) from exc
                raise
            added.extend(_added_ids(response))
            cursor = str(response.get("historyId", cursor))
            next_token = response.get("nextPageToken")
            if not next_token:
                break
            page_token = str(next_token)

        return MailboxChanges(added=tuple(dict.fromkeys(added)), cursor=cursor)

    def fetch(self, *, remote_id: str) -> FetchedMail:
        raw: Mapping[str, Any] = _execute(
            self._users.messages().get(userId="me", id=remote_id, format="full")
        )
        return to_fetched_mail(raw)


def _added_ids(response: Mapping[str, Any]) -> list[str]:
    added: list[str] = []
    records: list[Mapping[str, Any]] = response.get("history", [])
    for record in records:
        entries: list[Mapping[str, Any]] = record.get("messagesAdded", [])
        for entry in entries:
            message: Mapping[str, Any] = entry.get("message", {})
            if "id" in message:
                added.append(str(message["id"]))
    return added


# --- wire format -> domain ------------------------------------------------


def to_fetched_mail(raw: Mapping[str, Any]) -> FetchedMail:
    headers = message_headers(raw)
    return FetchedMail(
        remote_id=str(raw["id"]),
        thread_id=str(raw.get("threadId", raw["id"])),
        from_address=headers.get("from", ""),
        subject=headers.get("subject"),
        snippet=str(raw.get("snippet", "")),
        body=message_body(raw),
        received_at=received_at(raw, headers),
    )


def message_headers(raw: Mapping[str, Any]) -> dict[str, str]:
    payload: Mapping[str, Any] = raw.get("payload", {})
    headers: list[Mapping[str, Any]] = payload.get("headers", [])
    return {str(h["name"]).lower(): str(h["value"]) for h in headers}


def message_body(raw: Mapping[str, Any]) -> str:
    """The first text/plain part, falling back to the snippet."""
    return _find_text(raw.get("payload", {})) or str(raw.get("snippet", ""))


def _find_text(part: Mapping[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if part.get("mimeType") == "text/plain" and data:
        return base64.urlsafe_b64decode(str(data)).decode("utf-8", errors="replace")
    for child in part.get("parts", []):
        if text := _find_text(child):
            return text
    return ""


def received_at(raw: Mapping[str, Any], headers: Mapping[str, str]) -> datetime:
    """Gmail's `internalDate` is authoritative; the Date header is a fallback."""
    internal = raw.get("internalDate")
    if internal is not None:
        return datetime.fromtimestamp(int(internal) / 1000, tz=UTC)
    if date_header := headers.get("date"):
        try:
            return parsedate_to_datetime(date_header)
        except TypeError, ValueError:
            pass
    return datetime.now(UTC)
