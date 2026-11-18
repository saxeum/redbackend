from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import crud
from app.api.deps import ConnDep
from app.models import UserCreate, UserPublic

router = APIRouter(tags=["private"], prefix="/private")


class PrivateUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    is_verified: bool = False


@router.post("/users/", response_model=UserPublic)
def create_user(user_in: PrivateUserCreate, conn: ConnDep) -> Any:
    """
    Create a new user.
    """
    user_create = UserCreate(
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
    )
    return crud.create_user(conn=conn, user_create=user_create)
