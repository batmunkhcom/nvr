.PHONY: help setup setup-hook seed dev api web db redis minio infra test lint format build up down clean

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies
	pip install -e ".[dev]"

setup-hook: ## Install git pre-commit + post-commit hooks
	bash scripts/setup-hooks.sh

seed: ## Seed initial configuration to database
	python scripts/seed_db.py

dev: ## Start API dev server with hot reload
	cd services/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

api: ## Start API (production)
	cd services/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

web: ## Start React dev server
	cd services/web && npm install && npm run dev

# ----- Infrastructure -----

infra: ## Start infrastructure services (DB, Redis, MinIO)
	docker compose up -d db redis minio

db: ## Start only PostgreSQL
	docker compose up -d db

redis: ## Start only Redis
	docker compose up -d redis

minio: ## Start only MinIO
	docker compose up -d minio

# ----- Database -----

migrate: ## Run Alembic migrations
	cd services/api && alembic upgrade head

migrate-new: ## Create new Alembic migration (usage: make migrate-new msg="description")
	cd services/api && alembic revision --autogenerate -m "$(msg)"

migrate-down: ## Rollback last migration
	cd services/api && alembic downgrade -1

# ----- Testing -----

test: ## Run all tests
	python -m pytest -v

test-cov: ## Run tests with coverage report
	python -m pytest -v --cov=services --cov-report=term-missing

test-api: ## Run API tests only
	python -m pytest services/api/tests/ -v

# ----- Linting & Formatting -----

lint: ## Run Python linting
	ruff check services/

format: ## Format Python code
	ruff format services/

format-check: ## Check Python formatting
	ruff format --check services/

typecheck: ## Run type checker
	mypy services/

lint-web: ## Run TypeScript linting
	cd services/web && npx eslint src/

typecheck-web: ## Run TypeScript type checking
	cd services/web && npx tsc --noEmit

# ----- Docker -----

build: ## Build all Docker images
	docker compose build

build-api: ## Build API image only
	docker compose build api

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## View all service logs
	docker compose logs -f

logs-api: ## View API logs
	docker compose logs -f api

restart: ## Restart all services
	docker compose restart

# ----- Cleanup -----

clean: ## Remove Docker volumes and build cache
	docker compose down -v
	docker builder prune -f

clean-all: clean ## Also remove Python and Node cache
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf services/web/node_modules
	find . -name "*.pyc" -delete
