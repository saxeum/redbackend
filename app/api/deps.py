import uuid
from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app import crud
from app.core import security
from app.core.config import settings
from app.core.db import DBConnection, pool
from app.models import TokenPayload, UserRow

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Iterator[DBConnection]:
    # One transaction per request: committed on success, rolled back on error.
    with pool.connection() as conn:
        yield conn


ConnDep = Annotated[DBConnection, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(conn: ConnDep, token: TokenDep) -> UserRow:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    try:
        user_id = uuid.UUID(token_data.sub) if token_data.sub else None
    except ValueError:
        user_id = None
    user = crud.get_user_by_id(conn=conn, user_id=user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[UserRow, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> UserRow:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
