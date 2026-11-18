# Backend repository — FastAPI + PostgreSQL.
#
# Self-contained: no dependency on ../redfrontend.
# The only artifact shared with the frontend is the OpenAPI schema,
# exported with `make openapi` or fetched from the running API.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
UV      ?= uv
BUN     ?= $(shell command -v bun 2>/dev/null || printf '%s' "$$HOME/.bun/bin/bun")
API_URL ?= http://localhost:8000

# Email templates are authored with React Email and need Bun.
export PATH := $(dir $(BUN)):$(PATH)

##@ Getting started

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	/^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

doctor: ## Check tooling and required files
	@printf '%-14s' 'docker:'; if command -v docker >/dev/null 2>&1; then docker --version; else echo 'MISSING'; fi
	@printf '%-14s' 'compose:'; if docker compose version >/dev/null 2>&1; then docker compose version; else echo 'MISSING'; fi
	@printf '%-14s' 'uv:'; if command -v $(UV) >/dev/null 2>&1; then $(UV) --version; else echo 'MISSING'; fi
	@printf '%-14s' 'bun:'; if command -v $(BUN) >/dev/null 2>&1; then $(BUN) --version; else echo 'MISSING (optional, emails only)'; fi
	@printf '%-14s' '.env:'; if [ -f .env ]; then echo 'present'; else echo 'MISSING — cp .env.example .env'; fi

urls: ## Print local service URLs
	@echo 'Backend API:        http://localhost:8000'
	@echo 'API docs (Swagger): http://localhost:8000/docs'
	@echo 'Adminer:            http://localhost:8080'
	@echo 'Mailpit:            http://localhost:8025'

env-check: ## Verify .env exists
	@test -f .env || { echo 'Missing .env — run: cp .env.example .env'; exit 1; }

##@ Setup

setup: ## Install Python dependencies
	cd $(CURDIR) && $(UV) sync

bootstrap: env-check setup deps-up db-init ## One-shot: deps, DB, migrations, superuser
	@echo
	@echo 'Ready. Run: make dev'

##@ Development

deps-up: ## Start PostgreSQL, Mailpit, and Adminer
	$(COMPOSE) up -d db mailpit adminer

deps-down: ## Stop supporting services
	$(COMPOSE) stop db mailpit adminer

deps-logs: ## Follow supporting service logs
	$(COMPOSE) logs -f db mailpit

dev: deps-up ## Run the FastAPI dev server with reload (port 8000)
	cd $(CURDIR) && $(UV) run fastapi dev

##@ Database

db-init: deps-up ## Apply migrations and create the first superuser
	cd $(CURDIR) && $(UV) run bash scripts/prestart.sh

db-migrate: ## Apply pending Alembic migrations
	cd $(CURDIR) && $(UV) run alembic upgrade head

db-revision: ## Autogenerate a migration (usage: make db-revision m="message")
	@test -n "$(m)" || { echo 'Usage: make db-revision m="Add column x to User"'; exit 1; }
	cd $(CURDIR) && $(UV) run alembic revision --autogenerate -m "$(m)"

db-shell: ## Open a psql shell in the database container
	$(COMPOSE) exec db psql -U postgres -d app

db-reset: ## DESTRUCTIVE: drop containers and the database volume
	$(COMPOSE) down -v --remove-orphans

##@ Quality

lint: ## Run mypy, ty, and ruff checks
	cd $(CURDIR) && $(UV) run bash scripts/lint.sh

format: ## Auto-format with ruff
	cd $(CURDIR) && $(UV) run bash scripts/format.sh

##@ Tests

test: deps-up ## Run backend tests with coverage (WIPES users/items in dev DB)
	cd $(CURDIR) && $(UV) run bash scripts/test.sh

test-pytest: deps-up ## Run pytest subsets (WIPES data; e.g. ARGS="tests/api -k login -x")
	cd $(CURDIR) && FASTAPI_ENV=development $(UV) run pytest $(ARGS)

test-docker: ## Build the image and run tests inside Compose
	$(COMPOSE) build
	$(COMPOSE) run --rm backend bash scripts/prestart.sh
	$(COMPOSE) up -d --wait backend
	$(COMPOSE) exec -T backend bash scripts/tests-start.sh $(ARGS)

e2e-clean: ## Delete E2E test users/items (test_*@example.com) before frontend tests
	$(COMPOSE) exec -T db psql -U postgres -d app -c "delete from \"item\"; delete from \"user\" where email like 'test\\_%';"

##@ OpenAPI

openapi: ## Export openapi.json for the frontend repository
	cd $(CURDIR) && $(UV) run python -c 'import app.main, json; print(json.dumps(app.main.app.openapi()))' > openapi.json
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

##@ Email templates

email-setup: ## Install React Email dependencies
	cd $(CURDIR)/emails && $(BUN) install

email-dev: ## Preview email templates (port 3333)
	cd $(CURDIR)/emails && $(BUN) run dev

email-export: ## Regenerate app/email-templates from React Email
	cd $(CURDIR)/emails && $(BUN) run export

##@ Cleanup

clean: ## Remove caches and generated reports
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	@rm -rf htmlcov coverage .coverage openapi.json
	@echo 'Caches and generated reports removed.'

.PHONY: help doctor urls env-check setup bootstrap \
	deps-up deps-down deps-logs dev \
	db-init db-migrate db-revision db-shell db-reset \
	lint format test test-pytest test-docker e2e-clean \
	openapi docker-build docker-up docker-logs docker-shell docker-down \
	email-setup email-dev email-export clean
