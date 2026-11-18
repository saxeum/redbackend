import logging

from app import crud
from app.core.config import settings
from app.core.db import pool
from app.models import UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with pool.connection() as conn:
        user = crud.get_user_by_email(conn=conn, email=settings.FIRST_SUPERUSER)
        if not user:
            crud.create_user(
                conn=conn,
                user_create=UserCreate(
                    email=settings.FIRST_SUPERUSER,
                    password=settings.FIRST_SUPERUSER_PASSWORD,
                    is_superuser=True,
                ),
            )


def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
