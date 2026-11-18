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

## Full lifecycle

Every step is a Makefile target — no raw `docker` or `rm` commands needed.

```bash
make up          # deps + PostgreSQL + migrations + superuser + image + stack
make check       # basedpyright + ruff + pytest
make e2e         # HTTP smoke suite against the running stack
make verify      # check + reseed + e2e
make down        # stop the stack, keep the database volume
make teardown    # DESTRUCTIVE: containers, volumes, images, .venv, caches
make rebuild     # teardown + up + verify: the whole cycle from zero
```

`make rebuild` is the regression run. It removes every artifact (containers,
images, volume, `.venv`, caches), rebuilds the virtualenv from `uv.lock`, applies
migrations to an empty volume, seeds the superuser, builds the API image, then
runs lint, the test suite, and the HTTP smoke checks. `make e2e` accepts
`API_URL` to target another host (`API_URL=https://api.example.com make e2e`).

Intermediate states are available if you want them: `make setup`, `make deps-up`,
`make db-init`, `make docker-build`, `make docker-up`, `make db-reset`.

## Tests

```bash
make test                 # pytest + coverage, wipes users/items in the dev DB
make test-pytest ARGS='tests/api -k login -x'
make test-ci              # same suite, assumes PostgreSQL is already running
make e2e                  # HTTP smoke checks against a running stack
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
from `.venv`, and covers `app/`, `tests/` and `migrations/`. CI runs the same
`make lint`.

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

`app/api/schemas.py` holds the HTTP contract; `app/repositories/` holds the SQL.
See **Architecture** below for how the layers fit together.

## Architecture

Four layers, each with one job. Dependencies point inward: routes know about
services and schemas, services know about repositories and domain objects, and
nothing in `app/domain/` imports FastAPI.

```
app/api/        adapters: request/response schemas, mappers, routes, error handlers
app/services/   use cases: business rules, authorization, orchestration
app/domain/     entities, commands and typed errors (no I/O knowledge)
app/repositories/  SQL and row <-> domain mapping
```

- **`app/api/schemas.py`** — request and response models. Distinct from domain
  objects; request models are never passed to services.
- **`app/api/mappers.py`** — every conversion is explicit, in one place
  (`to_create_user`, `to_user_response`, ...). Renaming a field in one layer is
  a deliberate mapper change, never a silent contract change.
- **`app/services/`** — the only place business rules live: email uniqueness,
  superuser checks, ownership, password policy. They raise domain errors
  (`NotFound`, `PermissionDenied`, `Conflict`, `InvalidCredentials`, ...).
- **`app/repositories/`** — SQL only, returning domain objects. No FastAPI, no
  business rules, no request models.
- **`app/api/errors.py`** — maps each domain error to one HTTP status, so routes
  never raise `HTTPException` for business conditions.

Services take an already-open connection and commit when the use case completes
(before the response is sent), so a concurrent request never observes
uncommitted state; any raised error rolls the transaction back. Because services
have no HTTP or framework dependencies, they can be called from scripts, workers,
or a CLI use case as-is.

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
app/api/            FastAPI adapters: schemas, mappers, routes, errors, deps
app/services/       use cases and business rules
app/domain/         entities, commands, typed errors
app/repositories/   SQL and row mapping
migrations/         plain-SQL schema migrations + runner
tests/              pytest suite (api, services, mappers)
compose.yml         PostgreSQL, backend
Dockerfile          API-only image (no migrations)
Makefile            every development task (setup, db, lint, test, docker)
```
