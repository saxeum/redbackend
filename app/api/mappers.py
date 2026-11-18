"""Translation between presentation schemas and domain objects.

Every conversion is explicit: adding or renaming a field in one layer cannot
silently change the other.
"""

from app.api.schemas import (
    ItemCreateRequest,
    ItemListResponse,
    ItemResponse,
    ItemUpdateRequest,
    MailListResponse,
    MailMessageDetailResponse,
    MailMessageResponse,
    MailPollResponse,
    MeUpdateRequest,
    SignupRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.domain.commands import CreateItem, CreateUser, UpdateItem, UpdateUser
from app.domain.mail import MailMessage, PollResult
from app.domain.models import Item, User

# --- requests -> commands -------------------------------------------------


def to_create_user(payload: UserCreateRequest) -> CreateUser:
    return CreateUser(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        is_superuser=payload.is_superuser,
    )


def to_signup(payload: SignupRequest) -> CreateUser:
    return CreateUser(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
    )


def to_update_user(payload: UserUpdateRequest) -> UpdateUser:
    return UpdateUser(
        email=str(payload.email) if payload.email is not None else None,
        full_name=payload.full_name,
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
        password=payload.password,
        fields_set=frozenset(payload.model_fields_set),
    )


def to_me_update(payload: MeUpdateRequest) -> UpdateUser:
    return UpdateUser(
        email=str(payload.email) if payload.email is not None else None,
        full_name=payload.full_name,
        fields_set=frozenset(payload.model_fields_set),
    )


def to_create_item(payload: ItemCreateRequest) -> CreateItem:
    return CreateItem(title=payload.title, description=payload.description)


def to_update_item(payload: ItemUpdateRequest) -> UpdateItem:
    return UpdateItem(
        title=payload.title,
        description=payload.description,
        fields_set=frozenset(payload.model_fields_set),
    )


# --- domain -> responses --------------------------------------------------


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        has_password=user.hashed_password is not None,
        created_at=user.created_at,
    )


def to_user_list_response(users: list[User], count: int) -> UserListResponse:
    return UserListResponse(
        data=[to_user_response(user) for user in users], count=count
    )


def to_item_response(item: Item) -> ItemResponse:
    return ItemResponse(
        id=item.id,
        title=item.title,
        description=item.description,
        owner_id=item.owner_id,
        created_at=item.created_at,
    )


def to_item_list_response(items: list[Item], count: int) -> ItemListResponse:
    return ItemListResponse(
        data=[to_item_response(item) for item in items], count=count
    )


def to_mail_message_response(mail: MailMessage) -> MailMessageResponse:
    return MailMessageResponse(
        id=mail.id,
        mailbox=mail.mailbox,
        remote_id=mail.remote_id,
        thread_id=mail.thread_id,
        from_address=mail.from_address,
        subject=mail.subject,
        snippet=mail.snippet,
        received_at=mail.received_at,
    )


def to_mail_message_detail_response(mail: MailMessage) -> MailMessageDetailResponse:
    return MailMessageDetailResponse(
        **to_mail_message_response(mail).model_dump(), body=mail.body
    )


def to_mail_list_response(messages: list[MailMessage], count: int) -> MailListResponse:
    return MailListResponse(
        data=[to_mail_message_response(mail) for mail in messages], count=count
    )


def to_mail_poll_response(result: PollResult) -> MailPollResponse:
    return MailPollResponse(
        mailbox=result.mailbox,
        mode=result.mode,
        listed=result.listed,
        stored=result.stored,
        skipped=result.skipped,
        cursor=result.cursor,
    )
