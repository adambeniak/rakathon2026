#!/usr/bin/env bash
# Create the team's shared IRIS for Health Community container in Azure Container Instances.
# Hackathon only: ports are public over HTTP, storage is NOT persistent, use fictitious data only.
# Usage: IRIS_PASSWORD='...' ./scripts/aci_up.sh      (then: make iris-bootstrap IRIS_HOST=<ip>)
set -euo pipefail
: "${IRIS_PASSWORD:?Set IRIS_PASSWORD in your shell (never commit it)}"
RG="${RG:-rg-team73}"
NAME="${ACI_NAME:-aci-irishealth-team73}"
IMAGE="intersystems/irishealth-community@sha256:aad59884bdd89ee21c8cb059937c6b9b26947457641e5e04adecb68754376c6c"

az container create \
  --resource-group "$RG" \
  --name "$NAME" \
  --location swedencentral \
  --image "$IMAGE" \
  --os-type Linux --cpu 2 --memory 2 --restart-policy Never \
  --ip-address Public --dns-name-label "${DNS_LABEL:-stafeta-team73}" --ports 1972 52773 --protocol TCP \
  --secrets "iris-password=$IRIS_PASSWORD" \
  --secrets-mount-path /mnt/secrets \
  --command-line "/iris-main --password-file /mnt/secrets/iris-password" \
  --query "{state:provisioningState, ip:ipAddress.ip, fqdn:ipAddress.fqdn}" -o table

echo "Wait 2–5 minutes for IRIS to start, then check: bash scripts/aci_status.sh"
echo "Use the FQDN (stable across restarts) as IRIS_HOST and in FHIR_BASE_URL in .env."
echo "If the logs complain about the password file (read-only secret mount), tell the InterSystems mentors and develop locally."
echo "Portal: http://<IP>:52773/csp/sys/%25CSP.Portal.Home.zen  (user _SYSTEM)"
