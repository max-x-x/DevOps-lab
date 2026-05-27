#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
TMP_CONFIG="$(mktemp)"

cleanup() {
  rm -f "${TMP_CONFIG}"
}
trap cleanup EXIT

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.example to .env and fill TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in ${ENV_FILE}."
  exit 1
fi

if [[ ! "${TELEGRAM_CHAT_ID}" =~ ^-?[0-9]+$ ]]; then
  echo "TELEGRAM_CHAT_ID must be numeric (for example: 123456789 or -1001234567890)."
  exit 1
fi

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

cat > "${TMP_CONFIG}" <<EOF
global:
  resolve_timeout: 5m

route:
  receiver: "null"
  group_by:
    - alertname
    - namespace
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 2m
  routes:
    - receiver: telegram
      matchers:
        - namespace="lab5-app"
        - severity=~"warning|critical"

receivers:
  - name: "null"
  - name: telegram
    telegram_configs:
      - bot_token: "${TELEGRAM_BOT_TOKEN}"
        chat_id: ${TELEGRAM_CHAT_ID}
        parse_mode: HTML
        send_resolved: true
        message: |-
          <b>[{{ .Status | toUpper }}]</b> {{ .CommonLabels.alertname }}
          Namespace: {{ .CommonLabels.namespace }}
          Severity: {{ .CommonLabels.severity }}
          Summary: {{ .CommonAnnotations.summary }}
          Description: {{ .CommonAnnotations.description }}
EOF

kubectl create secret generic alertmanager-telegram-config \
  --namespace monitoring \
  --from-file=alertmanager.yaml="${TMP_CONFIG}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret alertmanager-telegram-config has been applied in namespace monitoring."
