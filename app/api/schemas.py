"""Presentation models: the HTTP contract.

Deliberately distinct from the domain objects in app/domain and from the
request/response shapes used elsewhere. Nothing here is imported by services
or repositories.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# --- request bodies -------------------------------------------------------


class UserCreateRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    is_superuser: bool = False


class SignupRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class MeUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class GoogleTokenRequest(BaseModel):
    """A Google OpenID Connect ID token, as issued to the SPA."""

    id_token: str = Field(min_length=1)


class ItemCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class ItemUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# --- response bodies ------------------------------------------------------


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_superuser: bool
    # False for accounts created through Google: they have no local password.
    has_password: bool
    created_at: datetime


class UserListResponse(BaseModel):
    data: list[UserResponse]
    count: int


class ItemResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    owner_id: uuid.UUID
    created_at: datetime


class ItemListResponse(BaseModel):
    data: list[ItemResponse]
    count: int


class MailMessageResponse(BaseModel):
    id: uuid.UUID
    mailbox: str
    remote_id: str
    thread_id: str
    from_address: str
    subject: str | None
    snippet: str
    received_at: datetime


class MailMessageDetailResponse(MailMessageResponse):
    body: str


class MailListResponse(BaseModel):
    data: list[MailMessageResponse]
    count: int


class MailPollResponse(BaseModel):
    mailbox: str
    mode: str
    listed: int
    stored: int
    skipped: int
    cursor: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    """Shape of every domain error returned by the API."""

    detail: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ConfigResponse(BaseModel):
    """Public runtime settings the SPA reads before it renders a login form."""

    password_login: bool
    google_login: bool
    google_client_id: str | None
