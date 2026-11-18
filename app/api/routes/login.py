from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import ConnDep, CurrentUser
from app.api.errors import api_responses
from app.api.mappers import to_user_response
from app.api.schemas import TokenResponse, UserResponse
from app.core import security
from app.core.config import settings
from app.domain.errors import ErrorCode
from app.services import users as user_service

router = APIRouter(tags=["login"])


@router.post(
    "/login/access-token",
    responses=api_responses(
        ErrorCode.INVALID_CREDENTIALS, ErrorCode.INACTIVE_USER, auth=False
    ),
)
def login_access_token(
    conn: ConnDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> TokenResponse:
    """OAuth2 compatible token login, get an access token for future requests."""
    user = user_service.authenticate(
        conn=conn, email=form_data.username, password=form_data.password
    )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return TokenResponse(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


@router.post(
    "/login/test-token",
    response_model=UserResponse,
    responses=api_responses(),
)
def test_token(current_user: CurrentUser) -> UserResponse:
    """Test access token."""
    return to_user_response(current_user)
