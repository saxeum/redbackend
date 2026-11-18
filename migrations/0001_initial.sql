-- Initial schema: users and items.
--
-- Written to be safe to run against a database that was created by the old
-- Alembic migrations: every statement is idempotent, and the Alembic version
-- table is dropped at the end.

CREATE TABLE IF NOT EXISTS "user" (
    id uuid PRIMARY KEY,
    email varchar(255) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    is_superuser boolean NOT NULL DEFAULT false,
    full_name varchar(255),
    hashed_password varchar NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON "user" (email);

CREATE TABLE IF NOT EXISTS item (
    id uuid PRIMARY KEY,
    title varchar(255) NOT NULL,
    description varchar(255),
    owner_id uuid NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_item_owner_id ON item (owner_id);

DROP TABLE IF EXISTS alembic_version;
