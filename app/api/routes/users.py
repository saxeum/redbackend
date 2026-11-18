import uuid

from fastapi import APIRouter

from app.api.deps import ConnDep, CurrentUser
from app.api.errors import api_responses
from app.api.mappers import (
    to_create_user,
    to_me_update,
    to_signup,
    to_update_user,
    to_user_list_response,
    to_user_response,
)
from app.api.schemas import (
    MessageResponse,
    MeUpdateRequest,
    PasswordChangeRequest,
    SignupRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.domain.errors import ErrorCode
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    response_model=UserListResponse,
    responses=api_responses(ErrorCode.INSUFFICIENT_PRIVILEGES),
)
def read_users(
    conn: ConnDep, actor: CurrentUser, skip: int = 0, limit: int = 100
) -> UserListResponse:
    """Retrieve users (superuser only)."""
    users, count = user_service.list_users(
        conn=conn, actor=actor, skip=skip, limit=limit
    )
    return to_user_list_response(users, count)


@router.post(
    "/",
    response_model=UserResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES, ErrorCode.EMAIL_TAKEN_ON_CREATE
    ),
)
def create_user(
    payload: UserCreateRequest, conn: ConnDep, actor: CurrentUser
) -> UserResponse:
    """Create a user (superuser only)."""
    user = user_service.create_user(conn=conn, cmd=to_create_user(payload), actor=actor)
    return to_user_response(user)


@router.patch(
    "/me",
    response_model=UserResponse,
    responses=api_responses(ErrorCode.EMAIL_TAKEN),
)
def update_user_me(
    payload: MeUpdateRequest, conn: ConnDep, actor: CurrentUser
) -> UserResponse:
    """Update own user."""
    user = user_service.update_me(conn=conn, actor=actor, cmd=to_me_update(payload))
    return to_user_response(user)


@router.patch(
    "/me/password",
    response_model=MessageResponse,
    responses=api_responses(ErrorCode.INCORRECT_PASSWORD, ErrorCode.PASSWORD_UNCHANGED),
)
def update_password_me(
    payload: PasswordChangeRequest, conn: ConnDep, actor: CurrentUser
) -> MessageResponse:
    """Update own password."""
    user_service.change_password(
        conn=conn,
        actor=actor,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password updated successfully")


@router.get("/me", response_model=UserResponse, responses=api_responses())
def read_user_me(actor: CurrentUser) -> UserResponse:
    """Get current user."""
    return to_user_response(actor)


@router.delete(
    "/me",
    response_model=MessageResponse,
    responses=api_responses(ErrorCode.SELF_DELETE_FORBIDDEN),
)
def delete_user_me(conn: ConnDep, actor: CurrentUser) -> MessageResponse:
    """Delete own user."""
    user_service.delete_me(conn=conn, actor=actor)
    return MessageResponse(message="User deleted successfully")


@router.post(
    "/signup",
    response_model=UserResponse,
    responses=api_responses(ErrorCode.EMAIL_TAKEN_ON_CREATE, auth=False),
)
def register_user(payload: SignupRequest, conn: ConnDep) -> UserResponse:
    """Create a new user without being logged in."""
    user = user_service.signup(conn=conn, cmd=to_signup(payload))
    return to_user_response(user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES, ErrorCode.USER_NOT_FOUND
    ),
)
def read_user_by_id(
    user_id: uuid.UUID, conn: ConnDep, actor: CurrentUser
) -> UserResponse:
    """Get a specific user by id."""
    return to_user_response(
        user_service.get_user(conn=conn, user_id=user_id, actor=actor)
    )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES,
        ErrorCode.USER_NOT_FOUND_FOR_UPDATE,
        ErrorCode.EMAIL_TAKEN,
    ),
)
def update_user(
    *,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    conn: ConnDep,
    actor: CurrentUser,
) -> UserResponse:
    """Update a user (superuser only)."""
    user = user_service.update_user(
        conn=conn, user_id=user_id, cmd=to_update_user(payload), actor=actor
    )
    return to_user_response(user)


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES,
        ErrorCode.USER_NOT_FOUND,
        ErrorCode.SELF_DELETE_FORBIDDEN,
    ),
)
def delete_user(
    user_id: uuid.UUID, conn: ConnDep, actor: CurrentUser
) -> MessageResponse:
    """Delete a user (superuser only)."""
    user_service.delete_user(conn=conn, user_id=user_id, actor=actor)
    return MessageResponse(message="User deleted successfully")
