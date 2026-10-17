#!/usr/bin/env bash
# `make up-local`: backend + mailpit + a LOCAL IRIS container (demo fallback when the team ACI is down).
#
# A fresh IRIS container needs a prepared password file (see iris_local_prepare.sh). A container that is already
# running is left alone: IRIS has consumed its password file, and rewriting it would only leave a plaintext copy behind.
# IRIS_SECRETS_DIR and ENV_FILE override the secrets directory and the env file (default: .iris and .env).
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.local-iris.yml)
dir="${IRIS_SECRETS_DIR:-.iris}"
env_file="${ENV_FILE:-.env}"

if ! "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx iris; then
  ./scripts/iris_local_prepare.sh
fi

# The backend container logs in with IRIS_PASSWORD from the env file; IRIS was given password.txt. If they differ the
# backend is rejected although IRIS itself is fine. Warn only; the values are never printed.
if [ -f "$env_file" ] && [ -s "$dir/password.txt" ]; then
  env_password="$(sed -n 's/^IRIS_PASSWORD=//p' "$env_file" | tail -n 1 | sed -e "s/^['\"]//" -e "s/['\"]$//")"
  if [ "$env_password" != "$(<"$dir/password.txt")" ]; then
    echo "WARNING: IRIS_PASSWORD in $env_file differs from $dir/password.txt: the backend will be rejected by the local IRIS." >&2
  fi
fi

"${COMPOSE[@]}" up -d --build
