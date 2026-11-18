"""The controller layer's message table: one entry per error code.

Both the HTTP status and the human-readable text are presentation decisions, so
they live here rather than in the domain or service layers.
"""

from dataclasses import dataclass

from app.domain.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class MessageSpec:
    status_code: int
    message: str


MESSAGES: dict[ErrorCode, MessageSpec] = {
    ErrorCode.ITEM_NOT_FOUND: MessageSpec(404, "Item not found"),
    ErrorCode.ITEM_PERMISSION_DENIED: MessageSpec(403, "Not enough permissions"),
    ErrorCode.USER_NOT_FOUND: MessageSpec(404, "User not found"),
    ErrorCode.USER_NOT_FOUND_FOR_UPDATE: MessageSpec(
        404, "The user with this id does not exist in the system"
    ),
    ErrorCode.INSUFFICIENT_PRIVILEGES: MessageSpec(
        403, "The user doesn't have enough privileges"
    ),
    ErrorCode.SELF_DELETE_FORBIDDEN: MessageSpec(
        403, "Super users are not allowed to delete themselves"
    ),
    ErrorCode.EMAIL_TAKEN: MessageSpec(409, "User with this email already exists"),
    ErrorCode.EMAIL_TAKEN_ON_CREATE: MessageSpec(
        400, "The user with this email already exists in the system"
    ),
    ErrorCode.GOOGLE_ACCOUNT_TAKEN: MessageSpec(
        409, "This Google account is already linked to another user"
    ),
    ErrorCode.INVALID_CREDENTIALS: MessageSpec(400, "Incorrect email or password"),
    ErrorCode.INCORRECT_PASSWORD: MessageSpec(400, "Incorrect password"),
    ErrorCode.INVALID_TOKEN: MessageSpec(401, "Could not validate credentials"),
    ErrorCode.EMAIL_NOT_ALLOWED: MessageSpec(
        403, "This account is not allowed to sign in"
    ),
    ErrorCode.PASSWORD_LOGIN_DISABLED: MessageSpec(404, "Password login is disabled"),
    ErrorCode.MAIL_NOT_CONFIGURED: MessageSpec(404, "Mail polling is not configured"),
    ErrorCode.MAIL_NOT_FOUND: MessageSpec(404, "Mail message not found"),
    ErrorCode.GOOGLE_LOGIN_DISABLED: MessageSpec(404, "Google login is disabled"),
    ErrorCode.INACTIVE_USER: MessageSpec(400, "Inactive user"),
    ErrorCode.PASSWORD_UNCHANGED: MessageSpec(
        400, "New password cannot be the same as the current one"
    ),
}
