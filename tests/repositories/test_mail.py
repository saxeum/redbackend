"""Mail repository tests against a real PostgreSQL (persistence is not mocked)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import DBConnection
from app.domain.mail import FetchedMail
from app.repositories import mail as mail_repo


def _mailbox() -> str:
    return f"mailbox-{uuid.uuid4().hex}@example.com"


def _fetched(remote_id: str, *, received_at: datetime | None = None) -> FetchedMail:
    return FetchedMail(
        remote_id=remote_id,
        thread_id=f"thread-{remote_id}",
        from_address="customer@example.com",
        subject="Hello",
        snippet="a snippet",
        body="the body",
        received_at=received_at or datetime.now(UTC),
    )


def test_insert_then_read_back(db: DBConnection) -> None:
    mailbox = _mailbox()
    fetched = _fetched("remote-1")

    stored = mail_repo.insert(conn=db, mailbox=mailbox, mail=fetched)

    assert stored is not None
    assert stored.mailbox == mailbox
    assert stored.remote_id == "remote-1"
    assert mail_repo.get_by_id(conn=db, mail_id=stored.id) == stored


def test_insert_is_idempotent_per_mailbox(db: DBConnection) -> None:
    mailbox = _mailbox()
    assert mail_repo.insert(conn=db, mailbox=mailbox, mail=_fetched("remote-1"))

    assert mail_repo.insert(conn=db, mailbox=mailbox, mail=_fetched("remote-1")) is None


def test_the_same_remote_id_is_stored_once_per_mailbox(db: DBConnection) -> None:
    first, second = _mailbox(), _mailbox()

    assert mail_repo.insert(conn=db, mailbox=first, mail=_fetched("shared"))
    assert mail_repo.insert(conn=db, mailbox=second, mail=_fetched("shared"))


def test_existing_ids_reports_only_known_messages(db: DBConnection) -> None:
    mailbox = _mailbox()
    mail_repo.insert(conn=db, mailbox=mailbox, mail=_fetched("known"))

    found = mail_repo.existing_ids(
        conn=db, mailbox=mailbox, remote_ids=["known", "unknown"]
    )

    assert found == {"known"}


def test_existing_ids_ignores_other_mailboxes(db: DBConnection) -> None:
    mail_repo.insert(conn=db, mailbox=_mailbox(), mail=_fetched("remote-1"))

    assert (
        mail_repo.existing_ids(conn=db, mailbox=_mailbox(), remote_ids=["remote-1"])
        == set()
    )


def test_existing_ids_with_no_candidates(db: DBConnection) -> None:
    assert mail_repo.existing_ids(conn=db, mailbox=_mailbox(), remote_ids=[]) == set()


def test_list_page_orders_by_received_at_desc(db: DBConnection) -> None:
    mailbox = _mailbox()
    older = _fetched("older", received_at=datetime.now(UTC) - timedelta(days=1))
    newer = _fetched("newer")
    mail_repo.insert(conn=db, mailbox=mailbox, mail=older)
    mail_repo.insert(conn=db, mailbox=mailbox, mail=newer)

    page, count = mail_repo.list_page(conn=db, skip=0, limit=100)
    remote_ids = [message.remote_id for message in page]

    assert count >= 2
    assert remote_ids.index("newer") < remote_ids.index("older")


def test_cursor_starts_absent(db: DBConnection) -> None:
    assert mail_repo.get_cursor(conn=db, mailbox=_mailbox()) is None


def test_cursor_roundtrip_and_advance(db: DBConnection) -> None:
    mailbox = _mailbox()

    mail_repo.set_cursor(conn=db, mailbox=mailbox, cursor="100")
    assert mail_repo.get_cursor(conn=db, mailbox=mailbox) == "100"

    mail_repo.set_cursor(conn=db, mailbox=mailbox, cursor="200")
    assert mail_repo.get_cursor(conn=db, mailbox=mailbox) == "200"


def test_cursor_is_per_mailbox(db: DBConnection) -> None:
    first, second = _mailbox(), _mailbox()
    mail_repo.set_cursor(conn=db, mailbox=first, cursor="100")

    assert mail_repo.get_cursor(conn=db, mailbox=second) is None
