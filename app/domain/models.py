"""Domain entities.

Plain dataclasses with no persistence or transport knowledge. `hashed_password`
is part of the user aggregate (the domain decides credentials) but is never
mapped into an API response.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    hashed_password: str | None
    created_at: datetime
    google_sub: str | None = None


@dataclass(frozen=True, slots=True)
class Item:
    id: uuid.UUID
    title: str
    description: str | None
    owner_id: uuid.UUID
    created_at: datetime
