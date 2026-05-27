#!/usr/bin/env bash
set -euo pipefail

echo "Scaling hello-app to 0 replicas to trigger alert HelloAppScaledToZero..."
kubectl scale deployment/hello-app --replicas=0 -n lab5-app

echo "Waiting 90 seconds so rule can move from Pending to Firing..."
sleep 90

echo "Current alert sample from Prometheus API:"
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" >/dev/null 2>&1 || true' EXIT
sleep 3
curl -sS "http://127.0.0.1:9090/api/v1/query?query=ALERTS%7Balertname%3D%22HelloAppScaledToZero%22%7D"

echo
echo "Restoring deployment to 2 replicas..."
kubectl scale deployment/hello-app --replicas=2 -n lab5-app

echo "Done. Check Alertmanager and Telegram for firing/resolved notifications."
