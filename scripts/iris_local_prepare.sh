#!/usr/bin/env bash
# Make the local-IRIS secrets directory ready for a FRESH container start (issue #43). Shared by `make up-local`
# (scripts/up_local.sh) and `make test-iris-local` (scripts/test_iris_local.sh), so the fix lives in one place.
#
# IRIS (`--password-file`) reads the password file ONCE and deletes it, then leaves a `password.done` sentinel next to
# it. A fresh container that finds a leftover sentinel skips the password change, keeps the image default and then
# rejects the password from password.txt. So this script
#   1. removes the sentinel,
#   2. hands IRIS a fresh copy of the password, without a trailing newline (IRIS tolerates one, verified; this only
#      keeps the value identical to IRIS_PASSWORD in .env, which never has one),
#   3. makes the directory writable for the container user, which has to delete that copy.
#
# Usage: scripts/iris_local_prepare.sh [--generate]
#   --generate  create password.txt with a random password when it is missing (test runs). Without it a missing file is
#               an error: `make up-local` needs the SAME value in .env (IRIS_PASSWORD) for the backend container.
# IRIS_SECRETS_DIR overrides the directory (default: .iris in the repo root; used by the script tests).
set -euo pipefail
cd "$(dirname "$0")/.."

dir="${IRIS_SECRETS_DIR:-.iris}"

if [ ! -s "$dir/password.txt" ]; then
  if [ "${1:-}" = "--generate" ]; then
    mkdir -p "$dir"
    python3 -c 'import secrets; print(secrets.token_urlsafe(18), end="")' > "$dir/password.txt"
  else
    echo "Put the local IRIS password into $dir/password.txt AND into .env as IRIS_PASSWORD" >&2
    echo "  (printf '%s' 'your-password' > $dir/password.txt   -- printf, not echo: no trailing newline)" >&2
    exit 1
  fi
fi

rm -f "$dir/password.done"
printf '%s' "$(<"$dir/password.txt")" > "$dir/password"
chmod 777 "$dir"
chmod 666 "$dir/password"
