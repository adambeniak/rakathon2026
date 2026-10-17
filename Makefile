# Štafeta — task runner. Phase F1 fills in the backend/frontend targets; keep target names stable,
# AGENTS.md and the prompts refer to them.
# NOTE: we deliberately do NOT `include .env` here (make keeps inline comments/spaces in values and would
# export secrets to every command). Env vars are passed to uv with --env-file instead.
SHELL := /bin/bash

.PHONY: up up-local down iris-bootstrap seed index check eval eval-ask-record vector-bench e2e demo-reset contract aci-up aci-status aci-down test-iris-local

up:            ## start backend + mailpit against the IRIS configured in .env (team ACI)
	docker compose up -d --build

up-local:      ## same + local IRIS container (demo fallback); a fresh container gets a clean password file (scripts/iris_local_prepare.sh)
	./scripts/up_local.sh

down:
	docker compose -f docker-compose.yml -f docker-compose.local-iris.yml down --remove-orphans

iris-bootstrap: ## idempotent: namespace, FHIR endpoint, vector table (re-run after every ACI restart)
	uv run --env-file .env --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py

test-iris-local: ## start ONLY the local IRIS container, bootstrap it, run `pytest -m iris` (no .env needed, never the ACI); PYTEST_ARGS='-k x'
	./scripts/test_iris_local.sh $(PYTEST_ARGS)

seed:          ## idempotent: directory, users, patient, the case and its 13 documents (scenario "story") + vector index
	cd backend && uv run --env-file ../.env python -m app.seed

index:         ## (re)build Stafeta.DocChunk from every DocumentReference; FORCE=1 re-embeds everything
	cd backend && uv run --env-file ../.env python -m app.retrieval.reindex $(if $(FORCE),--force,)

check:         ## lint + types + unit tests (skips parts that do not exist yet)
	@if [ -f backend/pyproject.toml ]; then cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -m "not iris" -q; else echo "backend/ not created yet - skipped"; fi
	@if [ -f frontend/package.json ]; then cd frontend && pnpm lint && pnpm typecheck && pnpm test --run; else echo "frontend/ not created yet - skipped"; fi

eval:          ## extraction + consistency vs data/golden, ask-the-case replay; report -> eval/report.json (repo root)
	cd backend && STAFETA_LLM_CACHE=$${STAFETA_LLM_CACHE:-1} uv run --env-file ../.env pytest tests/eval -q

eval-ask-record: ## live: re-record ask-the-case retrieval + LLM answers (needs seeded IRIS + APIM)
	cd backend && STAFETA_LLM_CACHE=0 uv run --env-file ../.env python -m tests.eval.ask_record

vector-bench:  ## live: latency of the IRIS retrieval layer (numbers for docs/vector-search.md)
	cd backend && uv run --env-file ../.env python -m tests.eval.vector_bench

e2e:           ## Playwright full demo flow with video
	cd frontend && pnpm exec playwright test

demo-reset:    ## delete everything tagged stafeta-demo, then seed directory, users and patient only (demo step 1 starts empty)
	cd backend && uv run --env-file ../.env python -m app.seed --reset --scenario demo-start

contract:      ## export OpenAPI + handover JSON Schema (via temp files, so a failed export never truncates a contract), regenerate the TS client
	cd backend && uv run python -m app.export_openapi > /tmp/stafeta-openapi.json && mv /tmp/stafeta-openapi.json ../contracts/openapi.json
	cd backend && uv run python -m app.export_schemas > /tmp/stafeta-handover.json && mv /tmp/stafeta-handover.json ../contracts/handover.schema.json
	@if [ -f frontend/package.json ]; then cd frontend && pnpm gen:api; else echo "frontend/ not created yet - TS client skipped"; fi

aci-up:
	bash scripts/aci_up.sh
aci-status:
	bash scripts/aci_status.sh
aci-down:
	bash scripts/aci_down.sh
