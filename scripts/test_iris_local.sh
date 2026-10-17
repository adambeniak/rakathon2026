#!/usr/bin/env bash
# Run the `-m iris` integration tests against a throw-away LOCAL IRIS container (issue #29).
# Needs no .env and never touches the team ACI: every connection setting is passed explicitly below, so a
# developer's .env (pointing at the ACI) cannot leak in. The password is local-only (.iris/password.txt, gitignored;
# generated on the first run).
#
# Usage: make test-iris-local [PYTEST_ARGS='-k referral']      (or ./scripts/test_iris_local.sh [pytest args])
# First run pulls the IRIS image and creates the FHIRSERVER namespace (several minutes); later runs reuse the
# running container and only repeat the idempotent bootstrap and seed. Stop it with:
#   docker compose -f docker-compose.yml -f docker-compose.local-iris.yml stop iris
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local-iris.yml)
LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

mkdir -p .iris
if [ ! -s .iris/password.txt ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(18), end="")' > .iris/password.txt
fi

if ! "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx iris; then
  # IRIS deletes its password file after reading it, so hand it a fresh copy on every start.
  # A leftover password.done sentinel from an earlier container makes IRIS skip the password change.
  rm -f .iris/password.done
  cp .iris/password.txt .iris/password
  chmod 777 .iris && chmod 666 .iris/password
  "${COMPOSE[@]}" up -d iris
fi

echo "waiting for local IRIS to become healthy ..."
cid="$("${COMPOSE[@]}" ps -q iris)"
for _ in $(seq 1 120); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] && break
  sleep 5
done
if [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" != healthy ]; then
  echo "local IRIS did not become healthy in 10 minutes: docker logs $cid" >&2
  exit 1
fi

export IRIS_HOST=localhost IRIS_SUPERSERVER_PORT=1972 IRIS_WEB_PORT=52773
export IRIS_NAMESPACE=FHIRSERVER IRIS_USER=_SYSTEM
IRIS_PASSWORD="$(<.iris/password.txt)"
export IRIS_PASSWORD
export FHIR_BASE_URL=http://localhost:52773/fhir/r4
export STAFETA_ENV=local STAFETA_DEMO_MODE=1 STAFETA_LLM_CACHE=1
unset STAFETA_ALLOW_SHARED_IRIS_TESTS

echo "bootstrapping the local namespace (idempotent) ..."
if ! uv run --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py > "$LOG_DIR/bootstrap.log" 2>&1; then
  tail -n 40 "$LOG_DIR/bootstrap.log" >&2
  echo "bootstrap failed; if the message says the credentials were rejected, delete the container and .iris/ and retry" >&2
  exit 1
fi

echo "seeding the demo case (idempotent; some iris tests need the seeded directory) ..."
if ! (cd backend && uv run python -m app.seed) > "$LOG_DIR/seed.log" 2>&1; then
  tail -n 40 "$LOG_DIR/seed.log" >&2
  exit 1
fi

echo "running pytest -m iris against localhost ..."
set +e
(cd backend && uv run pytest -m iris tests/integration -q -rs "$@") 2>&1 | tee "$LOG_DIR/pytest.log"
status="${PIPESTATUS[0]}"
set -e
# A skipped iris test means the guard refused the server or the container was unreachable: that is not a pass.
if [ "$status" -eq 0 ] && grep -Eq '[0-9]+ skipped' "$LOG_DIR/pytest.log"; then
  echo "FAIL: some iris tests were skipped, so the run proves nothing (see the skip reasons above)" >&2
  exit 1
fi
exit "$status"
