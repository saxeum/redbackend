import uuid
from typing import Any

import pytest
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings
from app.core.google import GoogleIdentity
from app.core.security import get_password_hash, verify_password
from app.domain.commands import CreateUser, UpdateUser
from app.domain.errors import (
    Conflict,
    ErrorCode,
    InactiveUser,
    InvalidCredentials,
    InvalidOperation,
    NotFound,
    PermissionDenied,
)
from app.services import users as user_service
from tests.fakes import CONN, install_user_repo, make_user


def _identity(
    *,
    subject: str = "google-subject-1",
    email: str = "person@example.com",
    name: str | None = "Person",
) -> GoogleIdentity:
    return GoogleIdentity(subject=subject, email=email, email_verified=True, name=name)


def test_create_user_requires_superuser(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(PermissionDenied) as exc:
        user_service.create_user(
            conn=CONN,
            cmd=CreateUser(email="new@example.com", password="password123"),
            actor=make_user(is_superuser=False),
        )

    assert exc.value.code is ErrorCode.INSUFFICIENT_PRIVILEGES


def test_create_user_persists_and_commits(monkeypatch: Any) -> None:
    repo, commits = install_user_repo(monkeypatch)

    created = user_service.create_user(
        conn=CONN,
        cmd=CreateUser(email="new@example.com", password="password123"),
        actor=make_user(is_superuser=True),
    )

    assert created.email == "new@example.com"
    assert created.is_active is True
    assert created.is_superuser is False
    assert repo.users[created.id] == created
    assert len(commits) == 1


def test_create_user_duplicate_email(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch, [make_user(email="taken@example.com")])

    with pytest.raises(Conflict) as exc:
        user_service.create_user(
            conn=CONN,
            cmd=CreateUser(email="taken@example.com", password="password123"),
            actor=make_user(is_superuser=True),
        )

    assert exc.value.code is ErrorCode.EMAIL_TAKEN_ON_CREATE


def test_signup_never_grants_superuser(monkeypatch: Any) -> None:
    repo, _ = install_user_repo(monkeypatch)

    created = user_service.signup(
        conn=CONN,
        cmd=CreateUser(
            email="new@example.com", password="password123", is_superuser=True
        ),
    )

    assert created.is_superuser is False
    assert repo.users[created.id].is_superuser is False


def test_authenticate_success(monkeypatch: Any) -> None:
    user = make_user(
        email="person@example.com", hashed_password=get_password_hash("password123")
    )
    _, commits = install_user_repo(monkeypatch, [user])

    authenticated = user_service.authenticate(
        conn=CONN, email="person@example.com", password="password123"
    )

    assert authenticated == user
    assert commits == []


def test_authenticate_unknown_email(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(InvalidCredentials) as exc:
        user_service.authenticate(
            conn=CONN, email="nobody@example.com", password="password123"
        )

    assert exc.value.code is ErrorCode.INVALID_CREDENTIALS


def test_authenticate_wrong_password(monkeypatch: Any) -> None:
    user = make_user(
        email="person@example.com", hashed_password=get_password_hash("password123")
    )
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidCredentials) as exc:
        user_service.authenticate(
            conn=CONN, email="person@example.com", password="wrongpassword"
        )

    assert exc.value.code is ErrorCode.INVALID_CREDENTIALS


def test_authenticate_inactive_user(monkeypatch: Any) -> None:
    user = make_user(
        email="person@example.com",
        hashed_password=get_password_hash("password123"),
        is_active=False,
    )
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InactiveUser) as exc:
        user_service.authenticate(
            conn=CONN, email="person@example.com", password="password123"
        )

    assert exc.value.code is ErrorCode.INACTIVE_USER


def test_authenticate_upgrades_bcrypt_hash(monkeypatch: Any) -> None:
    bcrypt_hash = BcryptHasher().hash("password123")
    user = make_user(email="legacy@example.com", hashed_password=bcrypt_hash)
    repo, commits = install_user_repo(monkeypatch, [user])

    authenticated = user_service.authenticate(
        conn=CONN, email="legacy@example.com", password="password123"
    )

    stored = repo.users[authenticated.id]
    assert stored.hashed_password is not None
    assert stored.hashed_password.startswith("$argon2")
    assert len(commits) == 1


def test_get_active_user_missing(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(NotFound) as exc:
        user_service.get_active_user(conn=CONN, user_id=uuid.uuid4())

    assert exc.value.code is ErrorCode.USER_NOT_FOUND


def test_get_active_user_inactive(monkeypatch: Any) -> None:
    user = make_user(is_active=False)
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InactiveUser):
        user_service.get_active_user(conn=CONN, user_id=user.id)


def test_get_user_self(monkeypatch: Any) -> None:
    user = make_user()
    install_user_repo(monkeypatch, [user])

    assert user_service.get_user(conn=CONN, user_id=user.id, actor=user) == user


def test_get_other_user_as_normal_user(monkeypatch: Any) -> None:
    actor = make_user(email="actor@example.com", is_superuser=False)
    other = make_user(email="other@example.com")
    install_user_repo(monkeypatch, [actor, other])

    with pytest.raises(PermissionDenied) as exc:
        user_service.get_user(conn=CONN, user_id=other.id, actor=actor)

    assert exc.value.code is ErrorCode.INSUFFICIENT_PRIVILEGES


def test_get_missing_user_as_superuser(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(NotFound) as exc:
        user_service.get_user(
            conn=CONN, user_id=uuid.uuid4(), actor=make_user(is_superuser=True)
        )

    assert exc.value.code is ErrorCode.USER_NOT_FOUND


def test_list_users_requires_superuser(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(PermissionDenied):
        user_service.list_users(
            conn=CONN, actor=make_user(is_superuser=False), skip=0, limit=10
        )


def test_list_users_returns_page(monkeypatch: Any) -> None:
    users = [make_user(email=f"user{i}@example.com") for i in range(3)]
    install_user_repo(monkeypatch, users)

    page, count = user_service.list_users(
        conn=CONN, actor=make_user(is_superuser=True), skip=0, limit=2
    )

    assert count == 3
    assert len(page) == 2


def test_update_user_missing(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(NotFound) as exc:
        user_service.update_user(
            conn=CONN,
            user_id=uuid.uuid4(),
            cmd=UpdateUser(full_name="X", fields_set=frozenset({"full_name"})),
            actor=make_user(is_superuser=True),
        )

    assert exc.value.code is ErrorCode.USER_NOT_FOUND_FOR_UPDATE


def test_update_user_email_conflict(monkeypatch: Any) -> None:
    first = make_user(email="first@example.com")
    second = make_user(email="second@example.com")
    install_user_repo(monkeypatch, [first, second])

    with pytest.raises(Conflict) as exc:
        user_service.update_user(
            conn=CONN,
            user_id=second.id,
            cmd=UpdateUser(email="first@example.com", fields_set=frozenset({"email"})),
            actor=make_user(is_superuser=True),
        )

    assert exc.value.code is ErrorCode.EMAIL_TAKEN


def test_update_user_applies_changes(monkeypatch: Any) -> None:
    user = make_user(email="person@example.com")
    repo, commits = install_user_repo(monkeypatch, [user])

    updated = user_service.update_user(
        conn=CONN,
        user_id=user.id,
        cmd=UpdateUser(full_name="Renamed", fields_set=frozenset({"full_name"})),
        actor=make_user(is_superuser=True),
    )

    assert updated.full_name == "Renamed"
    assert repo.users[user.id].full_name == "Renamed"
    assert len(commits) == 1


def test_update_me_can_clear_full_name(monkeypatch: Any) -> None:
    user = make_user(full_name="Old")
    install_user_repo(monkeypatch, [user])

    updated = user_service.update_me(
        conn=CONN,
        actor=user,
        cmd=UpdateUser(full_name=None, fields_set=frozenset({"full_name"})),
    )

    assert updated.full_name is None


def test_change_password_wrong_current(monkeypatch: Any) -> None:
    user = make_user(hashed_password=get_password_hash("password123"))
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidCredentials) as exc:
        user_service.change_password(
            conn=CONN,
            actor=user,
            current_password="wrongpassword",
            new_password="newpassword123",
        )

    assert exc.value.code is ErrorCode.INCORRECT_PASSWORD


def test_change_password_same_value(monkeypatch: Any) -> None:
    user = make_user(hashed_password=get_password_hash("password123"))
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidOperation) as exc:
        user_service.change_password(
            conn=CONN,
            actor=user,
            current_password="password123",
            new_password="password123",
        )

    assert exc.value.code is ErrorCode.PASSWORD_UNCHANGED


def test_change_password_updates_hash(monkeypatch: Any) -> None:
    user = make_user(hashed_password=get_password_hash("password123"))
    repo, commits = install_user_repo(monkeypatch, [user])

    user_service.change_password(
        conn=CONN,
        actor=user,
        current_password="password123",
        new_password="newpassword123",
    )

    stored = repo.users[user.id]
    assert stored.hashed_password is not None
    verified, _ = verify_password("newpassword123", stored.hashed_password)
    assert verified
    assert len(commits) == 1


def test_delete_user_requires_superuser(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch, [make_user()])

    with pytest.raises(PermissionDenied):
        user_service.delete_user(
            conn=CONN, user_id=uuid.uuid4(), actor=make_user(is_superuser=False)
        )


def test_delete_user_self_forbidden(monkeypatch: Any) -> None:
    admin = make_user(is_superuser=True)
    install_user_repo(monkeypatch, [admin])

    with pytest.raises(PermissionDenied) as exc:
        user_service.delete_user(conn=CONN, user_id=admin.id, actor=admin)

    assert exc.value.code is ErrorCode.SELF_DELETE_FORBIDDEN


def test_delete_missing_user(monkeypatch: Any) -> None:
    install_user_repo(monkeypatch)

    with pytest.raises(NotFound):
        user_service.delete_user(
            conn=CONN, user_id=uuid.uuid4(), actor=make_user(is_superuser=True)
        )


def test_delete_user_removes_and_commits(monkeypatch: Any) -> None:
    admin = make_user(email="admin@example.com", is_superuser=True)
    victim = make_user(email="victim@example.com")
    repo, commits = install_user_repo(monkeypatch, [admin, victim])

    user_service.delete_user(conn=CONN, user_id=victim.id, actor=admin)

    assert victim.id not in repo.users
    assert len(commits) == 1


def test_delete_me_forbidden_for_superuser(monkeypatch: Any) -> None:
    admin = make_user(is_superuser=True)
    install_user_repo(monkeypatch, [admin])

    with pytest.raises(PermissionDenied):
        user_service.delete_me(conn=CONN, actor=admin)


def test_delete_me_removes_and_commits(monkeypatch: Any) -> None:
    user = make_user()
    repo, commits = install_user_repo(monkeypatch, [user])

    user_service.delete_me(conn=CONN, actor=user)

    assert user.id not in repo.users
    assert len(commits) == 1


def test_authenticate_fails_when_password_login_is_disabled(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "ENABLE_PASSWORD_LOGIN", False)
    user = make_user(hashed_password=get_password_hash("password123"))
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidOperation) as exc:
        user_service.authenticate(conn=CONN, email=user.email, password="password123")

    assert exc.value.code is ErrorCode.PASSWORD_LOGIN_DISABLED


def test_authenticate_rejects_an_account_without_a_password(monkeypatch: Any) -> None:
    user = make_user(hashed_password=None, google_sub="google-subject-1")
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidCredentials) as exc:
        user_service.authenticate(conn=CONN, email=user.email, password="password123")

    assert exc.value.code is ErrorCode.INVALID_CREDENTIALS


def test_change_password_requires_a_local_password(monkeypatch: Any) -> None:
    user = make_user(hashed_password=None, google_sub="google-subject-1")
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InvalidCredentials) as exc:
        user_service.change_password(
            conn=CONN,
            actor=user,
            current_password="password123",
            new_password="newpassword123",
        )

    assert exc.value.code is ErrorCode.INCORRECT_PASSWORD


def test_google_login_creates_an_account(monkeypatch: Any) -> None:
    repo, commits = install_user_repo(monkeypatch)

    created = user_service.login_with_google(
        conn=CONN, identity=_identity(email="Person@Example.com")
    )

    assert created.email == "person@example.com"
    assert created.google_sub == "google-subject-1"
    assert created.full_name == "Person"
    assert created.hashed_password is None
    assert created.is_active is True
    assert created.is_superuser is False
    assert repo.users[created.id] == created
    assert len(commits) == 1


def test_google_login_returns_a_known_subject_without_writing(monkeypatch: Any) -> None:
    user = make_user(google_sub="google-subject-1")
    _, commits = install_user_repo(monkeypatch, [user])

    assert user_service.login_with_google(conn=CONN, identity=_identity()) == user
    assert commits == []


def test_google_login_links_an_existing_email(monkeypatch: Any) -> None:
    user = make_user(
        email="person@example.com", hashed_password=get_password_hash("password123")
    )
    repo, commits = install_user_repo(monkeypatch, [user])

    linked = user_service.login_with_google(conn=CONN, identity=_identity())

    assert linked.id == user.id
    assert repo.users[user.id].google_sub == "google-subject-1"
    # The local password keeps working: linking does not replace credentials.
    assert repo.users[user.id].hashed_password == user.hashed_password
    assert len(commits) == 1


def test_google_login_rejects_an_email_outside_the_allowlist(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "ALLOWED_EMAILS", "other@example.com")
    repo, commits = install_user_repo(monkeypatch)

    with pytest.raises(PermissionDenied) as exc:
        user_service.login_with_google(conn=CONN, identity=_identity())

    assert exc.value.code is ErrorCode.EMAIL_NOT_ALLOWED
    assert repo.users == {}
    assert commits == []


def test_google_allowlist_is_case_insensitive(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        settings, "ALLOWED_EMAILS", " Person@Example.com , other@example.com "
    )
    install_user_repo(monkeypatch)

    created = user_service.login_with_google(conn=CONN, identity=_identity())

    assert created.email == "person@example.com"


def test_google_login_rejects_an_inactive_linked_account(monkeypatch: Any) -> None:
    user = make_user(google_sub="google-subject-1", is_active=False)
    install_user_repo(monkeypatch, [user])

    with pytest.raises(InactiveUser) as exc:
        user_service.login_with_google(conn=CONN, identity=_identity())

    assert exc.value.code is ErrorCode.INACTIVE_USER


def test_google_login_does_not_link_an_inactive_account(monkeypatch: Any) -> None:
    user = make_user(email="person@example.com", is_active=False)
    repo, commits = install_user_repo(monkeypatch, [user])

    with pytest.raises(InactiveUser):
        user_service.login_with_google(conn=CONN, identity=_identity())

    assert repo.users[user.id].google_sub is None
    assert commits == []
