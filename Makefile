# Štafeta — task runner. Phase F1 fills in the backend/frontend targets; keep target names stable,
# AGENTS.md and the prompts refer to them.
# NOTE: we deliberately do NOT `include .env` here (make keeps inline comments/spaces in values and would
# export secrets to every command). Env vars are passed to uv with --env-file instead.
SHELL := /bin/bash

.PHONY: up up-local down iris-bootstrap seed check eval e2e demo-reset contract aci-up aci-status aci-down

up:            ## start backend + mailpit against the IRIS configured in .env (team ACI)
	docker compose up -d --build

up-local:      ## same + local IRIS container (demo fallback; IRIS deletes its password file after reading it, so copy it fresh)
	@test -s .iris/password.txt || { echo "Put the local IRIS password into .iris/password.txt AND into .env as IRIS_PASSWORD"; exit 1; }
	@cp .iris/password.txt .iris/password && chmod 777 .iris && chmod 666 .iris/password
	docker compose -f docker-compose.yml -f docker-compose.local-iris.yml up -d --build

down:
	docker compose -f docker-compose.yml -f docker-compose.local-iris.yml down --remove-orphans

iris-bootstrap: ## idempotent: namespace, FHIR endpoint, vector table (re-run after every ACI restart)
	uv run --env-file .env --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py

seed:          ## idempotent: directory, users, patient, the case and its 13 documents (scenario "story")
	cd backend && uv run --env-file ../.env python -m app.seed

check:         ## lint + types + unit tests (skips parts that do not exist yet)
	@if [ -f backend/pyproject.toml ]; then cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -m "not iris" -q; else echo "backend/ not created yet - skipped"; fi
	@if [ -f frontend/package.json ]; then cd frontend && pnpm lint && pnpm typecheck && pnpm test --run; else echo "frontend/ not created yet - skipped"; fi

eval:          ## extraction + consistency vs data/golden; report -> eval/report.json (repo root)
	cd backend && STAFETA_LLM_CACHE=$${STAFETA_LLM_CACHE:-1} uv run --env-file ../.env pytest tests/eval -q

e2e:           ## Playwright full demo flow with video
	cd frontend && pnpm exec playwright test

demo-reset:    ## delete everything tagged stafeta-demo, then seed directory, users and patient only (demo step 1 starts empty)
	cd backend && uv run --env-file ../.env python -m app.seed --reset --scenario demo-start

contract:      ## export OpenAPI + handover JSON Schema (via temp files, so a failed export never truncates a contract), regenerate the TS client
	cd backend && uv run python -m app.export_openapi > /tmp/stafeta-openapi.json && mv /tmp/stafeta-openapi.json ../contracts/openapi.json
	cd backend && uv run python -m app.export_schemas > /tmp/stafeta-handover.json && mv /tmp/stafeta-handover.json ../contracts/handover.schema.json
	@if [ -f frontend/package.json ]; then cd frontend && pnpm gen:api; else echo "frontend/ not created yet - TS client skipped"; fi

# --- extraction spike (spikes/extraction; moves to backend/ in PR ai/extraction-core) ---
SPIKE_EXTRACTION_UV := uv run -q --no-project --python 3.12 --with-requirements spikes/extraction/requirements.txt
.PHONY: spike-extraction-test spike-extraction-eval spike-extraction-fill-cache

spike-extraction-test:   ## offline unit tests + ruff + mypy --strict
	cd spikes/extraction && $(SPIKE_EXTRACTION_UV:spikes/extraction/%=%) --with ruff==0.12.8 --with mypy==1.17.1 \
	  sh -c 'ruff check . && ruff format --check . && mypy --strict --ignore-missing-imports --explicit-package-bases *.py && pytest -q -p no:cacheprovider'

spike-extraction-eval:   ## eval vs golden from the committed LLM cache (no network)
	STAFETA_LLM_CACHE=1 $(SPIKE_EXTRACTION_UV) python spikes/extraction/eval.py

spike-extraction-fill-cache: ## live APIM calls for cache misses (human runs this; needs .env)
	STAFETA_LLM_CACHE=0 $(SPIKE_EXTRACTION_UV) --env-file .env python spikes/extraction/eval.py

aci-up:
	bash scripts/aci_up.sh
aci-status:
	bash scripts/aci_status.sh
aci-down:
	bash scripts/aci_down.sh
