from app import crud
from app.core.db import DBConnection
from app.models import ItemCreate, ItemPublic
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def create_random_item(db: DBConnection) -> ItemPublic:
    user = create_random_user(db)
    title = random_lower_string()
    description = random_lower_string()
    item_in = ItemCreate(title=title, description=description)
    return crud.create_item(conn=db, item_in=item_in, owner_id=user.id)
