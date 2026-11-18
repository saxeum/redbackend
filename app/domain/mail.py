"""Mail domain objects.

`FetchedMail` is what a mail adapter hands over; `MailMessage` is that message
once it has a local identity. `MailboxProfile` and the cursor types let polling
be incremental instead of re-listing the inbox every cycle. Standard library
only, like the rest of the domain.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class FetchedMail:
    """A message read from a remote mailbox; no local identity yet."""

    remote_id: str
    thread_id: str
    from_address: str
    subject: str | None
    snippet: str
    body: str
    received_at: datetime


@dataclass(frozen=True, slots=True)
class MailboxProfile:
    """Where the remote mailbox currently is.

    `cursor` is the provider's opaque position token (Gmail's `historyId`).
    Store it after a successful sync and pass it back as `since` next time.
    """

    address: str
    cursor: str


@dataclass(frozen=True, slots=True)
class MailboxChanges:
    """What changed since a cursor, and where the mailbox is now."""

    added: tuple[str, ...]
    cursor: str


@dataclass(frozen=True, slots=True)
class MailMessage:
    id: uuid.UUID
    mailbox: str
    remote_id: str
    thread_id: str
    from_address: str
    subject: str | None
    snippet: str
    body: str
    received_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PollResult:
    """What one polling cycle did, for logs and the manual trigger."""

    mailbox: str
    mode: Literal["full", "incremental"]
    listed: int
    stored: int
    skipped: int
    cursor: str
