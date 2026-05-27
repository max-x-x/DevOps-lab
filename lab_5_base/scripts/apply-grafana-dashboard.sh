#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD_FILE="${ROOT_DIR}/monitoring/grafana/dashboards/lab5-overview.json"

if [[ ! -f "${DASHBOARD_FILE}" ]]; then
  echo "Dashboard file not found: ${DASHBOARD_FILE}"
  exit 1
fi

kubectl create configmap lab5-grafana-dashboard \
  --namespace monitoring \
  --from-file=lab5-overview.json="${DASHBOARD_FILE}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl label configmap lab5-grafana-dashboard \
  --namespace monitoring \
  grafana_dashboard=1 \
  --overwrite

echo "Grafana dashboard configmap applied: monitoring/lab5-grafana-dashboard"
