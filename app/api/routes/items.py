import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import ConnDep, CurrentUser
from app.models import ItemCreate, ItemPublic, ItemsPublic, ItemUpdate, Message

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/", response_model=ItemsPublic)
def read_items(
    conn: ConnDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve items.
    """
    owner_id = None if current_user.is_superuser else current_user.id
    items, count = crud.list_items(conn=conn, owner_id=owner_id, skip=skip, limit=limit)
    return ItemsPublic(data=items, count=count)


@router.get("/{id}", response_model=ItemPublic)
def read_item(conn: ConnDep, current_user: CurrentUser, id: uuid.UUID) -> Any:
    """
    Get item by ID.
    """
    item = crud.get_item(conn=conn, item_id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return item


@router.post("/", response_model=ItemPublic)
def create_item(
    *, conn: ConnDep, current_user: CurrentUser, item_in: ItemCreate
) -> Any:
    """
    Create new item.
    """
    return crud.create_item(conn=conn, item_in=item_in, owner_id=current_user.id)


@router.put("/{id}", response_model=ItemPublic)
def update_item(
    *,
    conn: ConnDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    item_in: ItemUpdate,
) -> Any:
    """
    Update an item.
    """
    item = crud.get_item(conn=conn, item_id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    updated = crud.update_item(conn=conn, item_id=id, item_in=item_in)
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return updated


@router.delete("/{id}")
def delete_item(conn: ConnDep, current_user: CurrentUser, id: uuid.UUID) -> Message:
    """
    Delete an item.
    """
    item = crud.get_item(conn=conn, item_id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    crud.delete_item(conn=conn, item_id=id)
    return Message(message="Item deleted successfully")
