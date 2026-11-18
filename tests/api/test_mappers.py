"""The presentation <-> domain translation is explicit; pin it down."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.api.mappers import (
    to_create_user,
    to_item_response,
    to_me_update,
    to_signup,
    to_update_user,
    to_user_response,
)
from app.api.schemas import (
    ItemUpdateRequest,
    MeUpdateRequest,
    SignupRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.domain.models import Item, User


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        email="person@example.com",
        full_name="Person",
        is_active=True,
        is_superuser=False,
        hashed_password="secret-hash",
        created_at=datetime.now(UTC),
    )


def test_user_response_never_exposes_the_hash() -> None:
    response = to_user_response(_user())

    payload = response.model_dump()
    assert "hashed_password" not in payload
    assert "secret-hash" not in response.model_dump_json()
    assert payload["email"] == "person@example.com"


def test_user_response_reports_whether_a_password_exists() -> None:
    assert to_user_response(_user()).has_password is True
    assert (
        to_user_response(replace(_user(), hashed_password=None)).has_password is False
    )


def test_create_user_mapping() -> None:
    cmd = to_create_user(
        UserCreateRequest(
            email="admin-made@example.com",
            password="password123",
            full_name="Made",
            is_superuser=True,
        )
    )

    assert cmd.email == "admin-made@example.com"
    assert cmd.is_superuser is True
    assert cmd.full_name == "Made"


def test_signup_mapping_has_no_privilege_field() -> None:
    cmd = to_signup(SignupRequest(email="new@example.com", password="password123"))

    assert cmd.email == "new@example.com"
    assert cmd.is_superuser is False


def test_update_mapping_tracks_supplied_fields() -> None:
    cmd = to_update_user(UserUpdateRequest(full_name="New Name"))

    assert cmd.full_name == "New Name"
    assert cmd.fields_set == frozenset({"full_name"})


def test_update_mapping_keeps_explicit_nulls() -> None:
    cmd = to_me_update(MeUpdateRequest.model_validate({"full_name": None}))

    assert "full_name" in cmd.fields_set
    assert cmd.full_name is None


def test_item_update_mapping_tracks_supplied_fields() -> None:
    from app.api.mappers import to_update_item

    cmd = to_update_item(ItemUpdateRequest(description=None))

    assert cmd.fields_set == frozenset({"description"})
    assert cmd.description is None


def test_item_response_mapping() -> None:
    owner_id = uuid.uuid4()
    item = Item(
        id=uuid.uuid4(),
        title="thing",
        description=None,
        owner_id=owner_id,
        created_at=datetime.now(UTC),
    )

    response = to_item_response(item)

    assert response.owner_id == owner_id
    assert response.title == "thing"
