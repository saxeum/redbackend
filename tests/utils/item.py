from app.core.db import DBConnection
from app.domain.commands import CreateItem
from app.domain.models import Item
from app.services import items as item_service
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def create_random_item(db: DBConnection) -> Item:
    user = create_random_user(db)
    return item_service.create_item(
        conn=db,
        cmd=CreateItem(title=random_lower_string(), description=random_lower_string()),
        actor=user,
    )
