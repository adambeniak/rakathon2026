#!/usr/bin/env bash
# Show state, public IP and the last log lines of the team IRIS container.
set -euo pipefail
RG="${RG:-rg-team73}"
NAME="${ACI_NAME:-aci-irishealth-team73}"
az container show -g "$RG" -n "$NAME" \
  --query "{state:instanceView.state, ip:ipAddress.ip, fqdn:ipAddress.fqdn, restarts:containers[0].instanceView.restartCount}" -o table
echo "--- last 20 log lines ---"
az container logs -g "$RG" -n "$NAME" | tail -n 20
