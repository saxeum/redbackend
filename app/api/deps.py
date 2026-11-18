import uuid
from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app.core import security
from app.core.config import settings
from app.core.db import DBConnection, pool
from app.core.google import is_google_token, verify_google_id_token
from app.core.security import TokenPayload
from app.domain.errors import (
    AuthenticationFailed,
    ErrorCode,
    NotFound,
)
from app.domain.models import User
from app.services import users as user_service

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Iterator[DBConnection]:
    # One transaction per request: committed on success, rolled back on error.
    with pool.connection() as conn:
        yield conn


ConnDep = Annotated[DBConnection, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(conn: ConnDep, token: TokenDep) -> User:
    if is_google_token(token):
        # OIDC resource server: the bearer credential is a Google ID token.
        identity = verify_google_id_token(token)
        return user_service.login_with_google(conn=conn, identity=identity)

    if not settings.ENABLE_PASSWORD_LOGIN:
        # Flipping the flag invalidates outstanding password-grant tokens too.
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)
    if not token_data.sub:
        raise AuthenticationFailed(ErrorCode.INVALID_TOKEN)
    try:
        user_id = uuid.UUID(token_data.sub)
    except ValueError:
        raise NotFound(ErrorCode.USER_NOT_FOUND)
    return user_service.get_active_user(conn=conn, user_id=user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
