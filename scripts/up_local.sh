#!/usr/bin/env bash
# `make up-local`: the demo fallback as ONE command. A LOCAL IRIS container, bootstrapped and seeded, plus backend and
# mailpit, ending with a health check that prints OK or FAIL (exit status 0 / 1).
#
#   make up-local                    # SCENARIO=demo-start: directory, users, patient; demo step 1 starts empty
#   make up-local SCENARIO=story     # the case with its 13 documents (also builds the vector index)
#
# 1. A fresh IRIS container gets a prepared password file (iris_local_prepare.sh). A container that is already
#    running is left alone: IRIS has consumed its password file, and rewriting it would only leave a copy behind.
# 2. The backend container gets the LOCAL password through the compose variable LOCAL_IRIS_PASSWORD, which only
#    docker-compose.local-iris.yml uses. The developer's env file (team ACI) stays untouched.
# 3. IRIS starts first; once healthy the namespace is bootstrapped and the scenario seeded from the host with explicit
#    connection settings (same helpers as test_iris_local.sh), and only then the backend starts.
# 4. The final check must pass: /api/health answers 200 (FHIR and IRIS SQL reachable) AND GET /api/cases as the demo
#    coordinator (X-Demo-Role) answers 200 (demo mode on, the seeded directory readable).
# IRIS_SECRETS_DIR, BACKEND_URL, BACKEND_HEALTH_ATTEMPTS and BACKEND_HEALTH_INTERVAL override the defaults.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/iris_local_lib.sh
source scripts/iris_local_lib.sh

SCENARIO="${SCENARIO:-demo-start}"
case "$SCENARIO" in
  demo-start | story) ;;
  *)
    echo "SCENARIO must be demo-start or story (got: $SCENARIO)" >&2
    exit 2
    ;;
esac
dir="$(iris_local_secrets_dir)"
LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

if ! iris_local_running; then
  ./scripts/iris_local_prepare.sh
fi
[ -s "$dir/password.txt" ] || fail "no local IRIS password in $dir/password.txt"
LOCAL_IRIS_PASSWORD="$(<"$dir/password.txt")"
export LOCAL_IRIS_PASSWORD

"${LOCAL_COMPOSE[@]}" up -d iris
iris_local_wait_healthy || fail "the local IRIS container is not healthy"
(
  iris_local_export_env && iris_local_bootstrap "$LOG_DIR" && iris_local_seed "$LOG_DIR" "$SCENARIO"
) || fail "bootstrap or seed of the local IRIS failed"

"${LOCAL_COMPOSE[@]}" up -d --build

backend="${BACKEND_URL:-http://127.0.0.1:8000}"
attempts="${BACKEND_HEALTH_ATTEMPTS:-40}" interval="${BACKEND_HEALTH_INTERVAL:-3}"
logs_hint="see: docker compose -f docker-compose.yml -f docker-compose.local-iris.yml logs backend"
show_body() { [ -s "$LOG_DIR/response.json" ] && head -c 600 "$LOG_DIR/response.json" >&2 && echo >&2 || true; }

code=000
for ((i = 0; i < attempts; i++)); do
  code="$(curl -s -o "$LOG_DIR/response.json" -w '%{http_code}' --max-time 20 "$backend/api/health" || true)"
  [ "$code" = 200 ] && break
  sleep "$interval"
done
if [ "$code" != 200 ]; then
  show_body
  fail "backend health check answered HTTP $code at $backend/api/health; $logs_hint"
fi

# Healthy is not enough: the demo API must answer too (demo roles on, seeded directory readable by the coordinator).
code="$(curl -s -o "$LOG_DIR/response.json" -w '%{http_code}' --max-time 20 -H 'X-Demo-Role: coordinator' "$backend/api/cases" || true)"
if [ "$code" != 200 ]; then
  show_body
  fail "GET /api/cases as the demo coordinator answered HTTP $code at $backend (demo mode on?); $logs_hint"
fi
echo "OK: backend healthy and GET /api/cases answers 200 at $backend (local IRIS, scenario $SCENARIO)"
