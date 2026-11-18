import uuid

from pwdlib.hashers.bcrypt import BcryptHasher

from app import crud
from app.core.db import DBConnection
from app.core.security import verify_password
from app.models import UserCreate, UserUpdate
from tests.utils.utils import random_email, random_lower_string


def test_create_user(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(conn=db, user_create=user_in)
    assert user.email == email
    assert user.hashed_password


def test_authenticate_user(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(conn=db, user_create=user_in)
    authenticated_user = crud.authenticate(conn=db, email=email, password=password)
    assert authenticated_user
    assert user.email == authenticated_user.email


def test_not_authenticate_user(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user = crud.authenticate(conn=db, email=email, password=password)
    assert user is None


def test_check_if_user_is_active(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(conn=db, user_create=user_in)
    assert user.is_active is True


def test_check_if_user_is_active_inactive(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password, is_active=False)
    user = crud.create_user(conn=db, user_create=user_in)
    assert user.is_active is False


def test_check_if_user_is_superuser(db: DBConnection) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password, is_superuser=True)
    user = crud.create_user(conn=db, user_create=user_in)
    assert user.is_superuser is True


def test_check_if_user_is_superuser_normal_user(db: DBConnection) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(conn=db, user_create=user_in)
    assert user.is_superuser is False


def test_get_user(db: DBConnection) -> None:
    password = random_lower_string()
    username = random_email()
    user_in = UserCreate(email=username, password=password, is_superuser=True)
    user = crud.create_user(conn=db, user_create=user_in)
    user_2 = crud.get_user_by_id(conn=db, user_id=user.id)
    assert user_2
    assert user.email == user_2.email
    assert user == user_2


def test_update_user(db: DBConnection) -> None:
    password = random_lower_string()
    email = random_email()
    user_in = UserCreate(email=email, password=password, is_superuser=True)
    user = crud.create_user(conn=db, user_create=user_in)
    new_password = random_lower_string()
    user_in_update = UserUpdate(password=new_password, is_superuser=True)
    crud.update_user(conn=db, user_id=user.id, user_in=user_in_update)
    user_2 = crud.get_user_by_id(conn=db, user_id=user.id)
    assert user_2
    assert user.email == user_2.email
    verified, _ = verify_password(new_password, user_2.hashed_password)
    assert verified
    assert user_2.is_superuser is True


def test_authenticate_user_with_bcrypt_upgrades_to_argon2(db: DBConnection) -> None:
    """Test that a user with bcrypt password hash gets upgraded to argon2 on login."""
    email = random_email()
    password = random_lower_string()

    # Create a bcrypt hash directly (simulating legacy password)
    bcrypt_hasher = BcryptHasher()
    bcrypt_hash = bcrypt_hasher.hash(password)
    assert bcrypt_hash.startswith("$2")  # bcrypt hashes start with $2

    # Create user with bcrypt hash directly in the database
    db.execute(
        'INSERT INTO "user" (id, email, is_active, is_superuser, hashed_password)'
        " VALUES (%s, %s, %s, %s, %s)",
        (uuid.uuid4(), email, True, False, bcrypt_hash),
    )

    # Authenticate - this should upgrade the hash to argon2
    authenticated_user = crud.authenticate(conn=db, email=email, password=password)
    assert authenticated_user
    assert authenticated_user.email == email

    refreshed = crud.get_user_by_id(conn=db, user_id=authenticated_user.id)
    assert refreshed

    # Verify the hash was upgraded to argon2
    assert refreshed.hashed_password.startswith("$argon2")

    verified, updated_hash = verify_password(password, refreshed.hashed_password)
    assert verified
    # Should not need another update since it's already argon2
    assert updated_hash is None
