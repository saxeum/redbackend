"""Item controller tests: services mocked, HTTP behaviour real."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.api.messages import MESSAGES
from app.domain.commands import UpdateItem
from app.domain.errors import ErrorCode, NotFound, PermissionDenied
from app.domain.models import Item, User
from tests.fakes import make_item, make_user

API = "/api/v1"


def detail(code: ErrorCode) -> str:
    return MESSAGES[code].message


def test_list_items_returns_page(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())
    items = [make_item(title="one"), make_item(title="two")]
    monkeypatch.setattr(
        "app.services.items.list_items",
        lambda *, conn, actor, skip, limit: (items, 2),
    )

    response = client.get(f"{API}/items/")

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [item["title"] for item in response.json()["data"]] == ["one", "two"]


def test_create_item_maps_request_to_command(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    actor = make_user()
    as_user(actor)
    captured: dict[str, Any] = {}

    def fake_create(*, conn: Any, cmd: Any, actor: User) -> Item:
        captured["cmd"] = cmd
        return make_item(title=cmd.title, description=cmd.description)

    monkeypatch.setattr("app.services.items.create_item", fake_create)

    response = client.post(f"{API}/items/", json={"title": "thing", "description": "d"})

    assert response.status_code == 200
    assert response.json()["title"] == "thing"
    assert captured["cmd"].title == "thing"
    assert captured["cmd"].description == "d"


def test_read_item_maps_response(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())
    item = make_item(title="thing", description="d")
    monkeypatch.setattr(
        "app.services.items.get_item", lambda *, conn, item_id, actor: item
    )

    response = client.get(f"{API}/items/{item.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(item.id)
    assert body["title"] == "thing"
    assert body["description"] == "d"
    assert body["owner_id"] == str(item.owner_id)
    assert "created_at" in body


def test_read_missing_item_is_404(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())

    def fake_get(*, conn: Any, item_id: Any, actor: User) -> Item:
        raise NotFound(ErrorCode.ITEM_NOT_FOUND)

    monkeypatch.setattr("app.services.items.get_item", fake_get)

    response = client.get(f"{API}/items/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.ITEM_NOT_FOUND)


def test_read_other_item_is_403(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())

    def fake_get(*, conn: Any, item_id: Any, actor: User) -> Item:
        raise PermissionDenied(ErrorCode.ITEM_PERMISSION_DENIED)

    monkeypatch.setattr("app.services.items.get_item", fake_get)

    response = client.get(f"{API}/items/{uuid.uuid4()}")

    assert response.status_code == 403
    assert response.json()["detail"] == detail(ErrorCode.ITEM_PERMISSION_DENIED)


def test_update_item_passes_only_supplied_fields(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())
    item = make_item(title="before", description="keep me")
    captured: dict[str, Any] = {}

    def fake_update(*, conn: Any, item_id: Any, cmd: UpdateItem, actor: User) -> Item:
        captured["cmd"] = cmd
        return make_item(title=cmd.title or item.title, description=item.description)

    monkeypatch.setattr("app.services.items.update_item", fake_update)

    response = client.put(f"{API}/items/{item.id}", json={"title": "after"})

    assert response.status_code == 200
    assert response.json()["title"] == "after"
    assert captured["cmd"].fields_set == frozenset({"title"})


def test_delete_item_returns_message(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())
    monkeypatch.setattr(
        "app.services.items.delete_item", lambda *, conn, item_id, actor: None
    )

    response = client.delete(f"{API}/items/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.json() == {"message": "Item deleted successfully"}


def test_delete_missing_item_is_404(
    client: TestClient,
    as_user: Callable[[User], None],
    monkeypatch: Any,
) -> None:
    as_user(make_user())

    def fake_delete(*, conn: Any, item_id: Any, actor: User) -> None:
        raise NotFound(ErrorCode.ITEM_NOT_FOUND)

    monkeypatch.setattr("app.services.items.delete_item", fake_delete)

    response = client.delete(f"{API}/items/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == detail(ErrorCode.ITEM_NOT_FOUND)
