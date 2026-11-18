"""The live OpenAPI document reflects the code: routes and error responses."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings

PREFIX = settings.API_V1_STR

REQUIRED_PATHS = {
    f"{PREFIX}/login/access-token",
    f"{PREFIX}/login/test-token",
    f"{PREFIX}/users/",
    f"{PREFIX}/users/me",
    f"{PREFIX}/users/me/password",
    f"{PREFIX}/users/signup",
    f"{PREFIX}/users/{{user_id}}",
    f"{PREFIX}/items/",
    f"{PREFIX}/items/{{id}}",
    f"{PREFIX}/utils/health-check/",
}


def _document(client: TestClient) -> dict[str, Any]:
    response = client.get(f"{PREFIX}/openapi.json")
    assert response.status_code == 200
    document: dict[str, Any] = response.json()
    return document


def test_documents_every_application_route(client: TestClient) -> None:
    paths = set(_document(client)["paths"])

    assert REQUIRED_PATHS <= paths
    private_path = f"{PREFIX}/private/users/"
    assert (private_path in paths) == settings.ENABLE_PRIVATE_ROUTER


def test_error_responses_are_documented(client: TestClient) -> None:
    document = _document(client)

    item = document["paths"][f"{PREFIX}/items/{{id}}"]["get"]["responses"]
    assert {"200", "404", "403", "503"} <= set(item)

    signup = document["paths"][f"{PREFIX}/users/signup"]["post"]["responses"]
    assert "400" in signup

    login = document["paths"][f"{PREFIX}/login/access-token"]["post"]["responses"]
    assert "400" in login


def test_error_response_component_is_referenced(client: TestClient) -> None:
    document = _document(client)

    component = document["components"]["schemas"]["ErrorResponse"]
    assert "detail" in component["properties"]

    not_found = document["paths"][f"{PREFIX}/items/{{id}}"]["get"]["responses"]["404"]
    schema = not_found["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/ErrorResponse")
