#!/usr/bin/env bash
# Run the `-m iris` integration tests against a throw-away LOCAL IRIS container (issue #29).
# Needs no env file and never touches the team ACI: every connection setting is passed explicitly (see
# iris_local_lib.sh), so a developer's env file (pointing at the ACI) cannot leak in. The password is local-only
# (secrets directory .iris, gitignored; generated on the first run).
#
# Usage: make test-iris-local [PYTEST_ARGS='-k referral']      (or ./scripts/test_iris_local.sh [pytest args])
# First run pulls the IRIS image and creates the FHIRSERVER namespace (several minutes); later runs reuse the
# running container and only repeat the idempotent bootstrap and seed. Stop it with:
#   docker compose -f docker-compose.yml -f docker-compose.local-iris.yml stop iris
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/iris_local_lib.sh
source scripts/iris_local_lib.sh

LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT
dir="$(iris_local_secrets_dir)"

mkdir -p "$dir"
if [ ! -s "$dir/password.txt" ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(18), end="")' > "$dir/password.txt"
fi

if ! iris_local_running; then
  # IRIS deletes its password file after reading it and a leftover password.done sentinel makes a fresh container skip
  # the password change: the shared helper (also used by `make up-local`) hands it a clean copy (issue #43).
  ./scripts/iris_local_prepare.sh --generate
  "${LOCAL_COMPOSE[@]}" up -d iris
fi

iris_local_wait_healthy || exit 1
# Subshell: the connection settings of the host-side bootstrap, seed and pytest stay out of this shell.
(
  iris_local_export_env && iris_local_bootstrap "$LOG_DIR" && iris_local_seed "$LOG_DIR" story || exit 1

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
)
