# Štafeta — task runner. Phase F1 fills in the backend/frontend targets; keep target names stable,
# AGENTS.md and the prompts refer to them.
# NOTE: we deliberately do NOT `include .env` here (make keeps inline comments/spaces in values and would
# export secrets to every command). Env vars are passed to uv with --env-file instead.
SHELL := /bin/bash

.PHONY: up down iris-bootstrap seed check eval e2e demo-reset contract aci-up aci-status aci-down

up:            ## start local stack (IRIS deletes its password file after reading it, so we copy it fresh each time)
	@test -s .iris/password.txt || { echo "Put the local IRIS password into .iris/password.txt AND into .env as IRIS_PASSWORD"; exit 1; }
	@cp .iris/password.txt .iris/password && chmod 777 .iris && chmod 666 .iris/password
	docker compose up -d

down:
	docker compose down

iris-bootstrap: ## idempotent: namespace, FHIR endpoint, vector table (re-run after every ACI restart)
	uv run --env-file .env --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py

seed:          ## load demo directory, users and documents (implemented in F1)
	cd backend && uv run --env-file ../.env python -m app.seed

check:         ## lint + types + unit tests (skips parts that do not exist yet)
	@if [ -f backend/pyproject.toml ]; then cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -m "not iris" -q; else echo "backend/ not created yet - skipped"; fi
	@if [ -f frontend/package.json ]; then cd frontend && pnpm lint && pnpm typecheck && pnpm test --run; else echo "frontend/ not created yet - skipped"; fi

eval:          ## extraction + consistency vs data/golden; report -> eval/report.json (repo root)
	cd backend && STAFETA_LLM_CACHE=$${STAFETA_LLM_CACHE:-1} uv run --env-file ../.env pytest tests/eval -q

e2e:           ## Playwright full demo flow with video
	cd frontend && pnpm exec playwright test

demo-reset:    ## wipe case data and re-seed
	cd backend && uv run --env-file ../.env python -m app.seed --reset

contract:      ## export OpenAPI (via temp file, so a failed export never truncates the contract) and regenerate the TS client
	cd backend && uv run python -m app.export_openapi > /tmp/stafeta-openapi.json && mv /tmp/stafeta-openapi.json ../contracts/openapi.json
	cd frontend && pnpm gen:api

aci-up:
	bash scripts/aci_up.sh
aci-status:
	bash scripts/aci_status.sh
aci-down:
	bash scripts/aci_down.sh
