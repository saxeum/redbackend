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

Testing is layered to match the code: each layer mocks the one below it.

| Layer | Tests | Dependencies |
|---|---|---|
| Controllers (`app/api`) | `tests/api/test_controllers_*`, `test_deps.py` | services mocked (`monkeypatch` + `app.dependency_overrides`) |
| Services (`app/services`) | `tests/services/` | repositories mocked (`tests/fakes.py`) |
| Core (`app/core`) | `tests/core/` | JWKS replaced with a locally generated key |
| Repositories (`app/repositories`) | `tests/repositories/` | **real PostgreSQL — not mocked** |
| Contract | `test_mappers.py`, `test_error_mapping.py`, `test_openapi.py` | none |
| Architecture | `test_layering.py` | none (AST) |
| End-to-end | `tests/e2e/smoke.py` | running stack (`make e2e`) |

```bash
make test                 # pytest + coverage, wipes users/items in the dev DB
make test-pytest ARGS='tests/services -k password -x'
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

## Authentication

Two ways to obtain a bearer credential:

| Flow | Endpoint | Credential |
|---|---|---|
| Google sign-in (OIDC) | `POST /api/v1/auth/google` | a Google **ID token** |
| Password grant (dev only) | `POST /api/v1/login/access-token` | our HS256 JWT |

**Google sign-in.** The SPA runs the Google flow and posts the resulting ID
token as `{"id_token": "..."}`. This service is an OIDC *resource server*: it
verifies the token against Google's JWKS (signature, `iss`, `aud`, `exp`) and
requires a verified email. The same ID token is then accepted as the bearer
credential on every authenticated route, so there is no server-side session.

`POST /auth/google` also resolves the token to a local account: first sign-in
creates a `user` row with no password; an email that already exists is *linked*
by storing Google's `sub` in `user.google_sub`, and the local password keeps
working. Accounts deactivated here cannot sign in through Google either.

Configuration (see `.env.example`):

| Variable | Meaning |
|---|---|
| `GOOGLE_CLIENT_ID` | audience the ID tokens are issued for. Shared with zuchat. Unset means Google sign-in fails closed. |
| `ALLOWED_EMAILS` | comma-separated allowlist of Google accounts. Empty means any verified account. |
| `ENABLE_PASSWORD_LOGIN` | `false` disables the password grant and rejects outstanding password-grant tokens. |

Only the client id is needed: the token's `aud` is that id, so no client secret
is stored here. The OAuth client's authorised redirect URIs belong to the
frontend. Invalid, expired or wrongly-scoped tokens return `401` with a generic
detail and a `WWW-Authenticate: Bearer` header; an account outside the
allowlist returns `403`.

**What the SPA reads.** `GET /api/v1/utils/config` returns
`{"password_login": bool, "google_client_id": str | null}`, so one image can
serve both modes: render the Google button when a client id is present and the
password form while `password_login` is on. `UserResponse.has_password` tells
the UI whether to offer "change password" — accounts created through Google
have none. Public self-registration (`POST /users/signup`) follows the same
flag, since it only exists to create password accounts.

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
  superuser checks, ownership, password policy. They raise domain errors that
  carry an `ErrorCode` (`NOT_FOUND`, `CONFLICT`, `INVALID_CREDENTIALS`, ...),
  never prose or HTTP statuses.
- **`app/repositories/`** — SQL only, returning domain objects. No FastAPI, no
  business rules, no request models. Driver failures are translated here
  (`UniqueViolation` becomes a domain `Conflict`).
- **`app/api/messages.py`** — the controller's strings table: one
  `(status_code, message)` per `ErrorCode`. Wording and statuses are
  presentation decisions and live only here.
- **`app/api/errors.py`** — registers one handler for `DomainError`, so a raised
  code is looked up in the table and decorated as `{"detail": …}`. Routes can
  call `error_response()` to override a status for one endpoint. Infrastructure
  failures (`OperationalError`, `PoolTimeout`) map to 503.

Services take an already-open connection and commit when the use case completes
(before the response is sent), so a concurrent request never observes
uncommitted state; any raised error rolls the transaction back. Because services
have no HTTP or framework dependencies, they can be called from scripts, workers,
or a CLI use case as-is.

## OpenAPI for the frontend

The frontend consumes this repository only through `openapi.json`, which is
**committed** so schema changes are reviewable and builds stay hermetic.

```bash
make openapi        # regenerate openapi.json from the app
make openapi-check  # fail if the committed file is stale (runs in CI)
```

The artifact is generated with `ENABLE_PRIVATE_ROUTER=false`, so the
development-only `/private/users/` route never leaks into the contract. Both
commands import the app — no running server is needed.

Error responses are generated from `app/api/messages.py`, so every documented
status matches the controller's strings table:

```json
"404": {"description": "Item not found",
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
```

For deploy verification, compare a running environment against the artifact
rather than generating from it:

```bash
curl -fsS "$API_URL/api/v1/openapi.json" -o /tmp/live.json
jq -S . /tmp/live.json > /tmp/live.sorted && jq -S . openapi.json > /tmp/artifact.sorted
diff /tmp/live.sorted /tmp/artifact.sorted
```

Against a development environment the only expected delta is
`/api/v1/private/users/`, which is mounted only when `ENABLE_PRIVATE_ROUTER=true`.
A production environment should match the artifact exactly.

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
