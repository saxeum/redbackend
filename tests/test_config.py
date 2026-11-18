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
