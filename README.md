# Backend

FastAPI + Pydantic + PostgreSQL API. This repository is standalone: it does not
import, build, or serve the frontend.

## Requirements

- Docker (PostgreSQL)
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
cp .env.example .env      # then change the secrets for anything non-local
make setup                # uv sync
make deps-up              # PostgreSQL
make db-init              # migrations + first superuser
make dev                  # FastAPI on :8000
```

| URL | Service |
|---|---|
| http://localhost:8000 | API |
| http://localhost:8000/docs | Swagger UI |

`make doctor` checks the local tooling; `make help` lists every target.

## Tests

```bash
make test                 # pytest + coverage, wipes users/items in the dev DB
make test-pytest ARGS='tests/api -k login -x'
make test-ci              # same suite, assumes PostgreSQL is already running
```

Coverage HTML is written to `htmlcov/index.html`.

Note: the test session deletes all users and items in the configured database.
Use `make db-seed` to restore the first superuser afterwards.

## Type checking and linting

`basedpyright` handles static types, `ruff` handles linting and formatting.
Both are pinned in `uv.lock` and configured in `pyproject.toml`, so the CLI and
the Zed language servers read the same settings:

```bash
make lint      # basedpyright + ruff check + ruff format --check
make format    # ruff format
```

`[tool.basedpyright]` sets `typeCheckingMode = "standard"`, resolves imports
from `.venv`, and covers `app/` and `tests/`. CI runs the same `make lint`.

## Migrations

Schema changes are plain SQL files in `migrations/`, applied in filename order
and recorded in the `schema_migrations` table. They run out of band from the
API: the container never migrates itself.

```bash
make db-migrate          # apply pending migrations
make db-seed             # migrations + first superuser
```

To change the schema, add `migrations/0002_<description>.sql`. Use
`IF NOT EXISTS` / `IF EXISTS` where a statement should be re-runnable, and keep
each file applied exactly once.

`app/models.py` holds the Pydantic DTOs; `app/crud.py` holds the SQL.

## OpenAPI for the frontend

The frontend is the only consumer of this repository, and only through the
OpenAPI schema:

```bash
make openapi     # writes openapi.json
```

Alternatively the frontend can fetch `http://localhost:8000/api/v1/openapi.json`
from a running server. Nothing else is shared between the two repositories.

## Docker

```bash
make docker-build
make docker-up
```

The image contains only the API. Serve the built frontend separately (static
hosting, nginx, ECS service behind the same ALB, etc.).

Migrations are not run by the container entrypoint. Apply them from the host,
pointing `DATABASE_URL` at the deployed database:

```bash
make db-migrate
```

## Layout

```
app/            FastAPI app, Pydantic DTOs, SQL in crud.py, routes
migrations/     plain-SQL schema migrations + runner
tests/          pytest suite
compose.yml     PostgreSQL, backend
Dockerfile      API-only image (no migrations)
Makefile        every development task (setup, db, lint, test, docker)
```
