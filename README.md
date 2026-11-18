# Backend

FastAPI + SQLModel + PostgreSQL API. This repository is standalone: it does not
import, build, or serve the frontend.

## Requirements

- Docker (PostgreSQL, Mailpit, Adminer)
- [uv](https://docs.astral.sh/uv/)
- Bun — optional, only for editing email templates

## Quick start

```bash
cp .env.example .env      # then change the secrets for anything non-local
make setup                # uv sync
make deps-up              # PostgreSQL + Mailpit + Adminer
make db-init              # migrations + first superuser
make dev                  # FastAPI on :8000
```

| URL | Service |
|---|---|
| http://localhost:8000 | API |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8080 | Adminer |
| http://localhost:8025 | Mailpit |

`make doctor` checks the local tooling; `make help` lists every target.

## Tests

```bash
make test                 # pytest + coverage, wipes users/items in the dev DB
make test-pytest ARGS='tests/api -k login -x'
make test-docker          # build the image and run the suite inside Compose
```

Coverage HTML is written to `htmlcov/index.html`.

Note: the test session deletes all users and items in the configured database.
Use `make db-init` to restore the first superuser afterwards.

## Migrations

Models live in `app/models.py`; CRUD in `app/crud.py`; routes in `app/api/`.

```bash
make db-revision m="Add column last_name to User"
make db-migrate
```

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

## Email templates

Templates are React Email components in `emails/`. The rendered HTML in
`app/email-templates/` is generated and committed.

```bash
make email-setup
make email-dev
make email-export
```

## Layout

```
app/            FastAPI app, models, CRUD, routes, Alembic migrations
tests/          pytest suite
scripts/        prestart, test, lint, format
emails/         React Email sources
compose.yml     PostgreSQL, Mailpit, Adminer, backend
Dockerfile      API-only image
```
