# Shared helpers for the scripts that work against the LOCAL IRIS container (`make up-local`, `make test-iris-local`).
# Sourced, not executed. The caller has already done `cd` to the repository root and `set -euo pipefail`.
#
# Every connection setting is passed explicitly (never taken from the developer's env file), so a file that points
# at the team ACI cannot leak into the host-side bootstrap and seed. The password is local-only (secrets dir).
# IRIS_SECRETS_DIR overrides the secrets directory (default: .iris); the *_ATTEMPTS / *_INTERVAL variables exist
# so the script tests do not have to wait.

LOCAL_COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local-iris.yml)

iris_local_secrets_dir() {
  echo "${IRIS_SECRETS_DIR:-.iris}"
}

# True when the local IRIS container is running (a running IRIS has consumed its password file: leave it alone).
iris_local_running() {
  "${LOCAL_COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx iris
}

iris_local_wait_healthy() {
  local attempts="${IRIS_HEALTH_ATTEMPTS:-120}" interval="${IRIS_HEALTH_INTERVAL:-5}" cid i
  echo "waiting for local IRIS to become healthy ..."
  cid="$("${LOCAL_COMPOSE[@]}" ps -q iris)"
  for ((i = 0; i < attempts; i++)); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] && return 0
    sleep "$interval"
  done
  echo "local IRIS did not become healthy in $((attempts * interval)) s: docker logs $cid" >&2
  return 1
}

# Connection settings for the HOST-side bootstrap and seed. Call it in a subshell: these variables must not leak into
# the `docker compose` calls.
iris_local_export_env() {
  export IRIS_HOST=localhost IRIS_SUPERSERVER_PORT=1972 IRIS_WEB_PORT=52773
  export IRIS_NAMESPACE=FHIRSERVER IRIS_USER=_SYSTEM
  IRIS_PASSWORD="$(<"$(iris_local_secrets_dir)/password.txt")"
  export IRIS_PASSWORD
  export FHIR_BASE_URL=http://localhost:52773/fhir/r4
  export STAFETA_ENV=local STAFETA_DEMO_MODE=1 STAFETA_LLM_CACHE=1
  unset STAFETA_ALLOW_SHARED_IRIS_TESTS
}

# iris_local_bootstrap LOG_DIR: namespace, FHIR endpoint, vector table (idempotent).
iris_local_bootstrap() {
  echo "bootstrapping the local namespace (idempotent) ..."
  if ! uv run --with intersystems-irispython==5.4.1 python scripts/bootstrap_iris.py > "$1/bootstrap.log" 2>&1; then
    tail -n 40 "$1/bootstrap.log" >&2
    echo "bootstrap failed; if the message says the credentials were rejected, delete the container and the secrets directory and retry" >&2
    return 1
  fi
}

# iris_local_seed LOG_DIR SCENARIO: the demo data (idempotent). The demo-start scenario seeds no documents, so it
# skips the embedding model (--no-index).
iris_local_seed() {
  local args=(--scenario "$2")
  [ "$2" = demo-start ] && args+=(--no-index)
  echo "seeding the $2 scenario (idempotent) ..."
  if ! (cd backend && uv run python -m app.seed "${args[@]}") > "$1/seed.log" 2>&1; then
    tail -n 40 "$1/seed.log" >&2
    return 1
  fi
}
