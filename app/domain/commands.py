"""Inputs to domain operations.

Commands are what the application layer passes to services. They are not
request models: adapters translate wire payloads into these.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateUser:
    email: str
    password: str
    full_name: str | None = None
    is_superuser: bool = False


@dataclass(frozen=True, slots=True)
class UpdateUser:
    email: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    password: str | None = None
    # Names of the fields the caller actually supplied; None means "leave as is".
    fields_set: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CreateItem:
    title: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateItem:
    title: str | None = None
    description: str | None = None
    fields_set: frozenset[str] = frozenset()
