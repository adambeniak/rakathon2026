#!/usr/bin/env bash
# Stop (default) or delete the team IRIS container. A running container is billed to the team budget
# and never stops by itself. Data is lost either way (non-persistent storage) — re-run
# `make iris-bootstrap && make seed` after the next start.
# Usage: ./scripts/aci_down.sh          # stop (keeps the container group, frees compute billing)
#        ./scripts/aci_down.sh delete   # delete completely
set -euo pipefail
RG="${RG:-rg-team73}"
NAME="${ACI_NAME:-aci-irishealth-team73}"
if [ "${1:-stop}" = "delete" ]; then
  az container delete -g "$RG" -n "$NAME" --yes
else
  az container stop -g "$RG" -n "$NAME"
  echo "Stopped. Start again with: az container start -g $RG -n $NAME"
fi
