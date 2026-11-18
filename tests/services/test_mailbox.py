"""Mailbox use cases: the mail client and the repository are faked."""

import uuid
from typing import Any

import pytest

from app.domain.errors import ErrorCode, NotFound, PermissionDenied
from app.services import mailbox as mailbox_service
from tests.fakes import (
    CONN,
    FakeMailClient,
    FakeMailRepository,
    install_mail_repo,
    make_fetched,
    make_mail,
    make_user,
)


def test_poll_new_stores_new_mail_and_commits(monkeypatch: Any) -> None:
    repo, commits = install_mail_repo(monkeypatch)
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a"), make_fetched(remote_id="b")]
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert result.mailbox == "inbox@example.com"
    assert (result.listed, result.stored, result.skipped) == (2, 2, 0)
    assert len(repo.messages) == 2
    assert commits == [CONN]


def test_poll_new_does_not_refetch_known_mail(monkeypatch: Any) -> None:
    known = make_mail(fetched=make_fetched(remote_id="a"))
    install_mail_repo(monkeypatch, [known])
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a"), make_fetched(remote_id="b")]
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert (result.listed, result.stored, result.skipped) == (2, 1, 1)
    assert client.fetched == ["b"]


def test_poll_new_honours_the_limit(monkeypatch: Any) -> None:
    install_mail_repo(monkeypatch)
    client = FakeMailClient(
        messages=[
            make_fetched(remote_id="a"),
            make_fetched(remote_id="b"),
            make_fetched(remote_id="c"),
        ]
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=2)

    assert result.listed == 2
    assert result.stored == 2


def test_poll_new_counts_a_lost_race_as_skipped(monkeypatch: Any) -> None:
    class RacingRepository(FakeMailRepository):
        def insert(self, *, conn: Any, mailbox: str, mail: Any) -> None:
            return None

    monkeypatch.setattr("app.services.mailbox.mail_repo", RacingRepository())
    monkeypatch.setattr("app.services.mailbox.commit", lambda conn: None)
    client = FakeMailClient(messages=[make_fetched(remote_id="a")])

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert (result.listed, result.stored, result.skipped) == (1, 0, 1)


def test_poll_new_with_no_mail_commits_nothing_useful(monkeypatch: Any) -> None:
    _, commits = install_mail_repo(monkeypatch)

    result = mailbox_service.poll_new(conn=CONN, client=FakeMailClient(), limit=10)

    assert (result.listed, result.stored, result.skipped) == (0, 0, 0)
    assert len(commits) == 1


def test_first_cycle_is_full_and_stores_the_cursor(monkeypatch: Any) -> None:
    repo, _ = install_mail_repo(monkeypatch)
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a"), make_fetched(remote_id="b")],
        cursor="900",
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert result.mode == "full"
    assert result.cursor == "900"
    assert repo.cursors == {"inbox@example.com": "900"}


def test_later_cycles_are_incremental(monkeypatch: Any) -> None:
    repo, commits = install_mail_repo(monkeypatch)
    repo.cursors["inbox@example.com"] = "900"
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a"), make_fetched(remote_id="b")],
        added=["b"],
        cursor="950",
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert result.mode == "incremental"
    assert (result.listed, result.stored, result.skipped) == (1, 1, 0)
    assert client.fetched == ["b"]
    assert repo.cursors["inbox@example.com"] == "950"
    assert len(commits) == 1


def test_incremental_skips_messages_already_stored(monkeypatch: Any) -> None:
    existing = make_mail(fetched=make_fetched(remote_id="a"))
    repo, _ = install_mail_repo(monkeypatch, [existing])
    repo.cursors["inbox@example.com"] = "900"
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a")], added=["a"], cursor="950"
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert (result.listed, result.stored, result.skipped) == (1, 0, 1)


def test_an_expired_cursor_falls_back_to_a_full_sync(monkeypatch: Any) -> None:
    repo, _ = install_mail_repo(monkeypatch)
    repo.cursors["inbox@example.com"] = "1"
    client = FakeMailClient(
        messages=[make_fetched(remote_id="a")], cursor="900", expired=True
    )

    result = mailbox_service.poll_new(conn=CONN, client=client, limit=10)

    assert result.mode == "full"
    assert result.stored == 1
    assert repo.cursors["inbox@example.com"] == "900"


def test_require_superuser_rejects_regular_users() -> None:
    with pytest.raises(PermissionDenied) as exc:
        mailbox_service.require_superuser(make_user(is_superuser=False))

    assert exc.value.code is ErrorCode.INSUFFICIENT_PRIVILEGES


def test_list_messages_requires_superuser(monkeypatch: Any) -> None:
    install_mail_repo(monkeypatch)

    with pytest.raises(PermissionDenied):
        mailbox_service.list_messages(conn=CONN, actor=make_user(), skip=0, limit=10)


def test_list_messages_returns_a_page(monkeypatch: Any) -> None:
    install_mail_repo(monkeypatch, [make_mail(), make_mail()])

    messages, count = mailbox_service.list_messages(
        conn=CONN, actor=make_user(is_superuser=True), skip=0, limit=10
    )

    assert count == 2
    assert len(messages) == 2


def test_get_message_requires_superuser(monkeypatch: Any) -> None:
    install_mail_repo(monkeypatch, [make_mail()])

    with pytest.raises(PermissionDenied):
        mailbox_service.get_message(conn=CONN, actor=make_user(), mail_id=uuid.uuid4())


def test_get_missing_message_is_not_found(monkeypatch: Any) -> None:
    install_mail_repo(monkeypatch)

    with pytest.raises(NotFound) as exc:
        mailbox_service.get_message(
            conn=CONN, actor=make_user(is_superuser=True), mail_id=uuid.uuid4()
        )

    assert exc.value.code is ErrorCode.MAIL_NOT_FOUND


def test_get_message_returns_the_stored_mail(monkeypatch: Any) -> None:
    mail = make_mail()
    install_mail_repo(monkeypatch, [mail])

    found = mailbox_service.get_message(
        conn=CONN, actor=make_user(is_superuser=True), mail_id=mail.id
    )

    assert found == mail
