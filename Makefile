# Backend repository — FastAPI + PostgreSQL.
#
# Self-contained: no dependency on ../redfrontend.
# The only artifact shared with the frontend is the OpenAPI schema,
# exported with `make openapi` or fetched from the running API.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
UV      ?= uv
API_URL ?= http://localhost:8000
PATHS   ?= app tests migrations

##@ Getting started

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	/^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

doctor: ## Check tooling and required files
	@printf '%-14s' 'docker:'; if command -v docker >/dev/null 2>&1; then docker --version; else echo 'MISSING'; fi
	@printf '%-14s' 'compose:'; if docker compose version >/dev/null 2>&1; then docker compose version; else echo 'MISSING'; fi
	@printf '%-14s' 'uv:'; if command -v $(UV) >/dev/null 2>&1; then $(UV) --version; else echo 'MISSING'; fi
	@printf '%-14s' '.env:'; if [ -f .env ]; then echo 'present'; else echo 'MISSING — cp .env.example .env'; fi

urls: ## Print local service URLs
	@echo 'Backend API:        http://localhost:8000'
	@echo 'API docs (Swagger): http://localhost:8000/docs'

env-check: ## Verify .env exists
	@test -f .env || { echo 'Missing .env — run: cp .env.example .env'; exit 1; }

##@ Setup

setup: ## Install Python dependencies
	$(UV) sync

bootstrap: env-check setup db-init ## One-shot: deps, DB, migrations, superuser
	@echo
	@echo 'Ready. Run: make dev'

##@ Development

deps-up: ## Start PostgreSQL
	$(COMPOSE) up -d --wait db

deps-down: ## Stop PostgreSQL
	$(COMPOSE) stop db

deps-logs: ## Follow PostgreSQL logs
	$(COMPOSE) logs -f db

dev: deps-up ## Run the FastAPI dev server with reload (port 8000)
	$(UV) run fastapi dev

##@ Database

db-init: deps-up db-seed ## Apply migrations and create the first superuser

db-migrate: ## Apply pending SQL migrations
	$(UV) run python -m migrations.run

db-seed: db-migrate ## Create the first superuser if missing
	$(UV) run python app/initial_data.py

db-shell: ## Open a psql shell in the database container
	$(COMPOSE) exec db psql -U postgres -d app

db-reset: ## DESTRUCTIVE: drop containers and the database volume
	$(COMPOSE) down -v --remove-orphans

##@ Quality

lint: ## Run basedpyright and ruff checks
	$(UV) run basedpyright
	$(UV) run ruff check $(PATHS)
	$(UV) run ruff format $(PATHS) --check

format: ## Auto-format with ruff
	$(UV) run ruff check $(PATHS) --fix
	$(UV) run ruff format $(PATHS)

##@ Tests

test: deps-up test-ci ## Run backend tests with coverage (WIPES users/items)

test-ci: ## Run tests against an already-running DB (used by CI)
	FASTAPI_ENV=development $(UV) run coverage run -m pytest tests/
	$(UV) run coverage report
	$(UV) run coverage html --title coverage

test-pytest: deps-up ## Run pytest subsets (WIPES data; e.g. ARGS="tests/api -k login -x")
	FASTAPI_ENV=development $(UV) run pytest $(ARGS)

##@ OpenAPI

openapi: ## Export openapi.json for the frontend repository
	$(UV) run python -c 'import app.main, json; print(json.dumps(app.main.app.openapi()))' > openapi.json
	@echo 'Wrote redbackend/openapi.json'
	@echo 'Frontend: copy it there or use OPENAPI_URL=$(API_URL)/api/v1/openapi.json'

##@ Docker

docker-build: ## Build the backend image
	$(COMPOSE) build

docker-up: ## Start the backend stack detached
	$(COMPOSE) up -d --wait

docker-logs: ## Follow stack logs
	$(COMPOSE) logs -f --tail=100

docker-shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

docker-down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

##@ Cleanup

clean: ## Remove caches and generated reports
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	@rm -rf htmlcov coverage .coverage openapi.json
	@echo 'Caches and generated reports removed.'

.PHONY: help doctor urls env-check setup bootstrap \
	deps-up deps-down deps-logs dev \
	db-init db-migrate db-seed db-shell db-reset \
	lint format test test-ci test-pytest \
	openapi docker-build docker-up docker-logs docker-shell docker-down \
	clean
