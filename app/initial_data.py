import logging

from app.core.config import settings
from app.core.db import pool
from app.services import users as user_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with pool.connection() as conn:
        user_service.ensure_superuser(
            conn=conn,
            email=str(settings.FIRST_SUPERUSER),
            password=settings.FIRST_SUPERUSER_PASSWORD,
        )


def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
