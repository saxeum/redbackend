"""Domain-level failures.

Services raise these instead of HTTP errors; the API layer maps them to
transport responses (see app/api/errors.py).
"""


class DomainError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    """The requested entity does not exist."""


class PermissionDenied(DomainError):
    """The actor may not perform this operation."""


class Conflict(DomainError):
    """The operation conflicts with existing state."""


class EmailAlreadyRegistered(Conflict):
    """A signup or admin create hit an existing email."""


class InvalidCredentials(DomainError):
    """Email/password combination is wrong."""


class InactiveUser(DomainError):
    """Credentials are valid but the account is disabled."""


class InvalidOperation(DomainError):
    """A request is well formed but not allowed in the current state."""
