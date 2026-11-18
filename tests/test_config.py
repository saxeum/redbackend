"""Settings helpers that affect deployment behaviour."""

from typing import Any

from app.core.config import settings


def test_frontend_origins_includes_configured_aliases(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "FRONTEND_HOST", "http://localhost:5173")
    monkeypatch.setattr(
        settings,
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5173, http://[::1]:5173",
    )

    assert settings.frontend_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ]


def test_frontend_origins_deduplicates_and_ignores_blanks(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "FRONTEND_HOST", "http://localhost:5173")
    monkeypatch.setattr(
        settings,
        "FRONTEND_ORIGINS",
        "http://localhost:5173,, http://[::1]:5173",
    )

    assert settings.frontend_origins == [
        "http://localhost:5173",
        "http://[::1]:5173",
    ]


def test_dev_origin_regex_accepts_local_ports(monkeypatch: Any) -> None:
    import re

    monkeypatch.setattr(settings, "FASTAPI_ENV", "development")
    pattern = settings.frontend_origin_regex

    assert pattern is not None
    for origin in (
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ):
        assert re.fullmatch(pattern, origin), origin
    assert not re.fullmatch(pattern, "https://example.com")


def test_origin_regex_is_disabled_outside_development(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "FASTAPI_ENV", None)

    assert settings.frontend_origin_regex is None
