#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl apply -f "${ROOT_DIR}/k8s/00-namespace.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/app/configmap.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/app/deployment.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/app/service.yaml"

bash "${ROOT_DIR}/scripts/create-telegram-secret.sh"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f "${ROOT_DIR}/helm/monitoring/values.yaml"

kubectl apply -f "${ROOT_DIR}/k8s/app/servicemonitor.yaml"
kubectl apply -f "${ROOT_DIR}/monitoring/prometheus/rules/app-alerts.yaml"
bash "${ROOT_DIR}/scripts/apply-grafana-dashboard.sh"

echo "Deployment completed."
