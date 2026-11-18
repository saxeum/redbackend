"""Domain-level failures.

Errors carry a machine-readable code only. Status codes and user-facing text
live in the controller layer (app/api/messages.py).
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    ITEM_NOT_FOUND = "item_not_found"
    ITEM_PERMISSION_DENIED = "item_permission_denied"
    USER_NOT_FOUND = "user_not_found"
    USER_NOT_FOUND_FOR_UPDATE = "user_not_found_for_update"
    INSUFFICIENT_PRIVILEGES = "insufficient_privileges"
    SELF_DELETE_FORBIDDEN = "self_delete_forbidden"
    EMAIL_TAKEN = "email_taken"
    EMAIL_TAKEN_ON_CREATE = "email_taken_on_create"
    GOOGLE_ACCOUNT_TAKEN = "google_account_taken"
    INVALID_CREDENTIALS = "invalid_credentials"
    INCORRECT_PASSWORD = "incorrect_password"
    INVALID_TOKEN = "invalid_token"
    EMAIL_NOT_ALLOWED = "email_not_allowed"
    PASSWORD_LOGIN_DISABLED = "password_login_disabled"
    MAIL_NOT_CONFIGURED = "mail_not_configured"
    MAIL_NOT_FOUND = "mail_not_found"
    GOOGLE_LOGIN_DISABLED = "google_login_disabled"
    INACTIVE_USER = "inactive_user"
    PASSWORD_UNCHANGED = "password_unchanged"


class DomainError(Exception):
    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class NotFound(DomainError):
    """The requested entity does not exist."""


class PermissionDenied(DomainError):
    """The actor may not perform this operation."""


class Conflict(DomainError):
    """The operation conflicts with existing state."""


class InvalidCredentials(DomainError):
    """The supplied credentials are wrong."""


class InactiveUser(DomainError):
    """Credentials are valid but the account is disabled."""


class AuthenticationFailed(DomainError):
    """The bearer token is missing, malformed, not decodable, or names a user
    that no longer exists."""


class InvalidOperation(DomainError):
    """A request is well formed but not allowed in the current state."""
