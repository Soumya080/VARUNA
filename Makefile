.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := PYTHONPATH=packages python

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── environment ──────────────────────────────────────────────────────────────
.PHONY: install
install: ## Install the project + dev extras (editable)
	pip install -e ".[dev]"

.PHONY: install-ml
install-ml: ## Add ML extras (torch, smp, mlflow)
	pip install -e ".[ml]"

.PHONY: install-physics
install-physics: ## OpenDrift via conda (pip resolution is unreliable)
	conda install -y -c opendrift -c conda-forge opendrift

# ── stack ────────────────────────────────────────────────────────────────────
.PHONY: up
up: ## Start the full dev stack
	docker compose up -d --build

.PHONY: up-infra
up-infra: ## Start postgres/redis/minio only (run api locally)
	docker compose up -d postgres redis minio

.PHONY: down
down: ## Stop the stack
	docker compose down

.PHONY: clean
clean: ## Stop and DELETE all volumes (destructive)
	docker compose down -v

.PHONY: logs
logs: ## Tail all logs
	docker compose logs -f

.PHONY: migrate
migrate: ## Apply database migrations
	alembic upgrade head

.PHONY: seed
seed: ## Load the shared CASE-0001 fixture
	bash infra/scripts/seed_case_0001.sh

# ── tests ────────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Fast tests: unit + contract (no services needed)
	$(PY) -m pytest tests/unit tests/contract -q

.PHONY: test-api
test-api: ## API + regression tests (no services needed)
	$(PY) -m pytest tests/api tests/regression -q

.PHONY: test-integration
test-integration: ## Integration tests (requires: make up-infra)
	$(PY) -m pytest tests/integration -q

.PHONY: test-scientific
test-scientific: ## Seeded numerical regression
	$(PY) -m pytest tests/scientific -q

.PHONY: test-robustness
test-robustness: ## Failure injection per FAILURE_THREAT_MATRIX.md
	$(PY) -m pytest tests/robustness -q

.PHONY: test-e2e
test-e2e: ## Full pipeline on CASE-0001
	$(PY) -m pytest tests/e2e -q

.PHONY: test-all
test-all: ## Everything
	$(PY) -m pytest tests -q

.PHONY: cov
cov: ## Coverage over the contract packages
	$(PY) -m pytest tests/unit tests/contract --cov=packages --cov-report=term-missing

# ── quality ──────────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## ruff
	ruff check packages apps tests

.PHONY: fmt
fmt: ## ruff --fix
	ruff check --fix packages apps tests

.PHONY: typecheck
typecheck: ## mypy
	mypy packages

.PHONY: security
security: ## bandit + pip-audit
	bandit -q -r packages apps -x tests
	pip-audit || true

.PHONY: check
check: lint typecheck test test-api ## Everything CI runs on a PR

# ── demo ─────────────────────────────────────────────────────────────────────
.PHONY: demo
demo: ## Run in DEMO_MODE (frozen artifacts, zero external calls)
	DEMO_MODE=true docker compose up -d --build

.PHONY: verify-offline
verify-offline: ## Assert DEMO_MODE makes no external network calls
	$(PY) -m pytest tests/e2e -q -k offline

.PHONY: demo-m35
demo-m35: ## Run the M3.5 offline demo script
	$(PY) scripts/demo_m35.py
