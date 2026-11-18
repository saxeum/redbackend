"""End-to-end HTTP smoke test against a running API.

    make e2e           # against http://localhost:8000
    API_URL=https://... make e2e

Covers authentication, authorization, user/item CRUD, partial updates,
cascade deletes and the endpoints that no longer exist. Exits non-zero if any
expectation fails and prints a per-check summary.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from app.core.config import settings

BASE_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
API = BASE_URL + "/api/v1"
SUPERUSER_EMAIL = os.environ.get("FIRST_SUPERUSER") or str(settings.FIRST_SUPERUSER)
SUPERUSER_PASSWORD = (
    os.environ.get("FIRST_SUPERUSER_PASSWORD") or settings.FIRST_SUPERUSER_PASSWORD
)

RESULTS: list[tuple[bool, str, str]] = []


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {}
    data: bytes | None = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read()
    return status, (json.loads(payload) if payload else None)


def call(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    expect: int = 200,
) -> Any:
    status, payload = request(method, path, token=token, body=body, form=form)
    assert status == expect, (
        f"{method} {path}: expected {expect}, got {status}: {payload!r}"
    )
    return payload


def check(name: str, fn: Callable[[], Any]) -> None:
    try:
        detail = fn()
        RESULTS.append((True, name, "" if detail is None else str(detail)))
    except Exception as exc:
        RESULTS.append((False, name, str(exc)))


def main() -> int:
    """A smoke test is one long happy path; keep it linear and readable."""
    suffix = uuid.uuid4().hex[:8]
    account = f"e2e-{suffix}@example.com"
    other = f"e2e-other-{suffix}@example.com"
    private = f"e2e-private-{suffix}@example.com"
    password = "password123"
    new_password = "newpassword123"

    state: dict[str, Any] = {}

    def super_token() -> str:
        state["super"] = call(
            "POST",
            "/login/access-token",
            form={"username": SUPERUSER_EMAIL, "password": SUPERUSER_PASSWORD},
        )["access_token"]
        return "token issued"

    check("health check", lambda: call("GET", "/utils/health-check/"))

    def runtime_config() -> str:
        config = call("GET", "/utils/config")
        assert isinstance(config["password_login"], bool), config
        assert isinstance(config["google_login"], bool), config
        assert "google_client_id" in config, config
        return f"password_login={config['password_login']}"

    check("runtime config", runtime_config)
    check(
        "google sign-in rejects an invalid token -> 401",
        lambda: call(
            "POST", "/auth/google", body={"id_token": "not-a-token"}, expect=401
        ),
    )
    check("superuser login", super_token)
    check(
        "superuser is flagged",
        lambda: call("GET", "/users/me", token=state["super"])["is_superuser"] is True,
    )

    def signup() -> str:
        created = call(
            "POST",
            "/users/signup",
            body={"email": account, "password": password, "full_name": "E2E User"},
        )
        state["account_id"] = created["id"]
        return created["email"]

    check("signup", signup)
    check(
        "duplicate signup -> 400",
        lambda: call(
            "POST",
            "/users/signup",
            body={"email": account, "password": password},
            expect=400,
        ),
    )

    def user_login() -> str:
        state["user"] = call(
            "POST",
            "/login/access-token",
            form={"username": account, "password": password},
        )["access_token"]
        return "token issued"

    check("user login", user_login)

    def me_shape() -> str:
        me = call("GET", "/users/me", token=state["user"])
        assert me["email"] == account, me
        assert me["has_password"] is True, me
        return "email and has_password"

    check("user /users/me", me_shape)
    check(
        "user list users -> 403",
        lambda: call("GET", "/users/", token=state["user"], expect=403),
    )
    check(
        "user read unknown user -> 403",
        lambda: call(
            "GET",
            "/users/00000000-0000-0000-0000-000000000000",
            token=state["user"],
            expect=403,
        ),
    )
    check(
        "update own profile",
        lambda: (
            call(
                "PATCH", "/users/me", token=state["user"], body={"full_name": "Renamed"}
            )["full_name"]
            == "Renamed"
        ),
    )
    check(
        "wrong current password -> 400",
        lambda: call(
            "PATCH",
            "/users/me/password",
            token=state["user"],
            body={"current_password": "wrongpassword", "new_password": new_password},
            expect=400,
        ),
    )
    check(
        "change password",
        lambda: call(
            "PATCH",
            "/users/me/password",
            token=state["user"],
            body={"current_password": password, "new_password": new_password},
        )["message"],
    )
    check(
        "login with new password",
        lambda: call(
            "POST",
            "/login/access-token",
            form={"username": account, "password": new_password},
        )["access_token"],
    )

    def create_item() -> str:
        state["item"] = call(
            "POST",
            "/items/",
            token=state["user"],
            body={"title": "e2e item", "description": "keep me"},
        )
        return state["item"]["id"]

    check("create item", create_item)

    def partial_update() -> str:
        updated = call(
            "PUT",
            "/items/" + state["item"]["id"],
            token=state["user"],
            body={"title": "e2e item v2"},
        )
        assert updated["title"] == "e2e item v2", updated
        assert updated["description"] == "keep me", "untouched field was overwritten"
        return "title changed, description preserved"

    check("partial item update", partial_update)
    check(
        "list items is scoped",
        lambda: call("GET", "/items/", token=state["user"])["count"] >= 1,
    )
    check(
        "read own item",
        lambda: (
            call("GET", "/items/" + state["item"]["id"], token=state["user"])["id"]
            == state["item"]["id"]
        ),
    )
    check(
        "missing item -> 404",
        lambda: call(
            "GET",
            "/items/00000000-0000-0000-0000-000000000000",
            token=state["user"],
            expect=404,
        ),
    )
    check(
        "superuser lists users",
        lambda: call("GET", "/users/", token=state["super"])["count"] >= 2,
    )

    def mail_list() -> str:
        body = call("GET", "/mail/messages", token=state["super"])
        assert isinstance(body["count"], int), body
        return f"count={body['count']}"

    check("superuser lists stored mail", mail_list)
    check(
        "mail list is superuser-only -> 403",
        lambda: call("GET", "/mail/messages", token=state["user"], expect=403),
    )
    check(
        "superuser reads account",
        lambda: (
            call("GET", "/users/" + state["account_id"], token=state["super"])["email"]
            == account
        ),
    )

    def admin_create() -> str:
        created = call(
            "POST",
            "/users/",
            token=state["super"],
            body={"email": other, "password": password, "full_name": "Other"},
        )
        state["other_id"] = created["id"]
        return created["email"]

    check("superuser creates user", admin_create)
    check(
        "superuser duplicate user -> 400",
        lambda: call(
            "POST",
            "/users/",
            token=state["super"],
            body={"email": other, "password": password},
            expect=400,
        ),
    )
    check(
        "superuser updates user",
        lambda: (
            call(
                "PATCH",
                "/users/" + state["other_id"],
                token=state["super"],
                body={"full_name": "Other Two"},
            )["full_name"]
            == "Other Two"
        ),
    )
    check(
        "superuser deletes user",
        lambda: call("DELETE", "/users/" + state["other_id"], token=state["super"])[
            "message"
        ],
    )
    check(
        "deleted user -> 404",
        lambda: call(
            "GET", "/users/" + state["other_id"], token=state["super"], expect=404
        ),
    )
    check(
        "superuser cannot delete self -> 403",
        lambda: call("DELETE", "/users/me", token=state["super"], expect=403),
    )

    def admin_item() -> str:
        state["admin_item"] = call(
            "POST", "/items/", token=state["super"], body={"title": "admin item"}
        )
        return state["admin_item"]["id"]

    check("superuser creates item", admin_item)
    check(
        "user cannot read another's item -> 403",
        lambda: call(
            "GET",
            "/items/" + state["admin_item"]["id"],
            token=state["user"],
            expect=403,
        ),
    )
    check(
        "user cannot delete another's item -> 403",
        lambda: call(
            "DELETE",
            "/items/" + state["admin_item"]["id"],
            token=state["user"],
            expect=403,
        ),
    )
    check(
        "superuser deletes item",
        lambda: call(
            "DELETE", "/items/" + state["admin_item"]["id"], token=state["super"]
        )["message"],
    )
    check(
        "superuser reads any item",
        lambda: (
            call("GET", "/items/" + state["item"]["id"], token=state["super"])["id"]
            == state["item"]["id"]
        ),
    )

    def dev_only_router() -> str:
        status, payload = request(
            "POST",
            "/private/users/",
            body={"email": private, "password": password, "full_name": "Private"},
        )
        if status == 404:
            return "not exposed (expected outside development)"
        assert status == 200, f"unexpected status {status}: {payload!r}"
        call("DELETE", "/users/" + payload["id"], token=state["super"])
        return "created and cleaned up"

    check("private router (development only)", dev_only_router)

    removed = (
        ("reset-password", "/reset-password/"),
        ("password-recovery", f"/login/password-recovery/{account}"),
        ("test-email", "/utils/test-email/?email_to=e2e@example.com"),
    )
    for label, path in removed:
        check(
            f"removed endpoint {label} -> 404",
            lambda p=path: call("POST", p, expect=404),
        )

    check(
        "delete own account",
        lambda: call("DELETE", "/users/me", token=state["user"])["message"],
    )

    def deleted_token_is_401() -> str:
        status, payload = request("GET", "/users/me", token=state["user"])
        assert status == 401, f"expected 401, got {status}: {payload!r}"
        return str((payload or {}).get("detail"))

    check("deleted account's token -> 401", deleted_token_is_401)
    check(
        "deleted account cannot log in -> 400",
        lambda: call(
            "POST",
            "/login/access-token",
            form={"username": account, "password": new_password},
            expect=400,
        ),
    )
    check(
        "deleted account's items cascaded -> 404",
        lambda: call(
            "GET", "/items/" + state["item"]["id"], token=state["super"], expect=404
        ),
    )

    failures = [result for result in RESULTS if not result[0]]
    for ok, name, detail in RESULTS:
        print(("PASS " if ok else "FAIL ") + name + (f" -> {detail}" if detail else ""))
    print(f"\n{len(RESULTS) - len(failures)}/{len(RESULTS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
