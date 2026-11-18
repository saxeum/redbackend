import uuid

from fastapi import APIRouter

from app.api.deps import ConnDep, CurrentUser
from app.api.errors import api_responses
from app.api.mappers import (
    to_create_item,
    to_item_list_response,
    to_item_response,
    to_update_item,
)
from app.api.schemas import (
    ItemCreateRequest,
    ItemListResponse,
    ItemResponse,
    ItemUpdateRequest,
    MessageResponse,
)
from app.domain.errors import ErrorCode
from app.services import items as item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/", response_model=ItemListResponse, responses=api_responses())
def read_items(
    conn: ConnDep, actor: CurrentUser, skip: int = 0, limit: int = 100
) -> ItemListResponse:
    """Retrieve items visible to the caller."""
    items, count = item_service.list_items(
        conn=conn, actor=actor, skip=skip, limit=limit
    )
    return to_item_list_response(items, count)


@router.get(
    "/{id}",
    response_model=ItemResponse,
    responses=api_responses(ErrorCode.ITEM_NOT_FOUND, ErrorCode.ITEM_PERMISSION_DENIED),
)
def read_item(id: uuid.UUID, conn: ConnDep, actor: CurrentUser) -> ItemResponse:
    """Get an item by id."""
    return to_item_response(item_service.get_item(conn=conn, item_id=id, actor=actor))


@router.post("/", response_model=ItemResponse, responses=api_responses())
def create_item(
    payload: ItemCreateRequest, conn: ConnDep, actor: CurrentUser
) -> ItemResponse:
    """Create a new item owned by the caller."""
    item = item_service.create_item(conn=conn, cmd=to_create_item(payload), actor=actor)
    return to_item_response(item)


@router.put(
    "/{id}",
    response_model=ItemResponse,
    responses=api_responses(ErrorCode.ITEM_NOT_FOUND, ErrorCode.ITEM_PERMISSION_DENIED),
)
def update_item(
    *,
    id: uuid.UUID,
    payload: ItemUpdateRequest,
    conn: ConnDep,
    actor: CurrentUser,
) -> ItemResponse:
    """Update an item the caller may access."""
    item = item_service.update_item(
        conn=conn, item_id=id, cmd=to_update_item(payload), actor=actor
    )
    return to_item_response(item)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    responses=api_responses(ErrorCode.ITEM_NOT_FOUND, ErrorCode.ITEM_PERMISSION_DENIED),
)
def delete_item(id: uuid.UUID, conn: ConnDep, actor: CurrentUser) -> MessageResponse:
    """Delete an item the caller may access."""
    item_service.delete_item(conn=conn, item_id=id, actor=actor)
    return MessageResponse(message="Item deleted successfully")
