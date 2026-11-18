from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ConnDep
from app.api.mappers import to_user_response
from app.api.schemas import UserResponse
from app.domain.commands import CreateUser
from app.services import users as user_service

router = APIRouter(tags=["private"], prefix="/private")


class PrivateUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    is_verified: bool = False


@router.post("/users/", response_model=UserResponse)
def create_user(user_in: PrivateUserCreate, conn: ConnDep) -> UserResponse:
    """Create a new user (development-only router)."""
    user = user_service.signup(
        conn=conn,
        cmd=CreateUser(
            email=user_in.email,
            password=user_in.password,
            full_name=user_in.full_name,
        ),
    )
    return to_user_response(user)
