# AASP Metrics Adapter

Polls Huawei AASP `infer-recommendations` API, takes **max** over `resources.predictions`, and exposes Prometheus gauges for Kthena Autoscaler (`metricEndpoint` Pod scrape).

## Leader election (recommended)

Run the adapter on **every** ModelServing pod. Enable `LEADER_ELECTION=1` so pods compete for a Kubernetes `Lease`:

- **Leader**: polls AASP (or MOCK) and exposes real predicted gauges
- **Followers**: skip AASP polls; expose `0` for predicted gauges

Kthena can scrape **all** pods; the sum equals the global peak (no ×N). If the leader pod is scaled down, another pod acquires the lease within ~`LEASE_DURATION_SECONDS`.

Requires a ServiceAccount that can `get/create/update` `leases` in the namespace (see `deploy.yaml`).

## Metrics

| Metric | Source |
|--------|--------|
| `aasp_predicted_rpm` | `max(predictions[].rpm)` (leader only; followers `0`) |
| `aasp_predicted_prompt_tpm` | `max(predictions[].prompt_tpm)` (leader only; followers `0`) |
| `aasp_predicted_completion_tpm` | `max(predictions[].completion_tpm)` (leader only; followers `0`) |
| `aasp_predicted_total_tpm` | `max(predictions[].total_tpm)` (optional) |
| `aasp_predicted_latency_ms` | `max(predictions[].latency)` (optional) |
| `aasp_adapter_up` | `1` if leader and last fetch OK |
| `aasp_adapter_is_leader` | `1` if this pod holds the lease |

On fetch failure the leader **keeps the last good values** and sets `aasp_adapter_up=0`.

## API

```text
GET {BASE_URL}/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations
    ?region=...&start_time=...&end_time=...
Authorization: Bearer {TOKEN}
```

Peak strategy: window max over `predictions` (not `score`, until that field is documented).

## Environment

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `BASE_URL` | no | `https://apigw-beta.huawei.com` | beta or `https://apigw.huawei.com` |
| `PROJECT_ID` | yes* | | path project id |
| `SERVICE_GROUP_ID` | yes* | | prediction unit id |
| `REGION` | recommended | | query region |
| `TOKEN` | yes* | | bearer token |
| `WINDOW_MINUTES` | no | `5` | `end_time - start_time` |
| `POLL_SECONDS` | no | `15` | poll interval |
| `METRICS_PORT` | no | `8000` | `/metrics` port |
| `MOCK` | no | `0` | `1` = offline mock values |
| `MOCK_RPM` / `MOCK_PROMPT_TPM` / `MOCK_COMPLETION_TPM` | no | | used when `MOCK=1` |
| `LEADER_ELECTION` | no | `0` | `1` = Kubernetes Lease election |
| `LEASE_NAME` | no | `aasp-metrics-leader` | Lease object name |
| `LEASE_DURATION_SECONDS` | no | `15` | lease TTL |
| `LEASE_RENEW_SECONDS` | no | `5` | renew interval |
| `POD_NAME` | yes if election | | downward API `metadata.name` |
| `POD_NAMESPACE` | yes if election | | downward API `metadata.namespace` |

\* Not required when `MOCK=1`.

## Local run

```bash
cd aasp-metrics-adapter

# Offline demo (no election)
MOCK=1 MOCK_RPM=300 PROJECT_ID=p SERVICE_GROUP_ID=s python adapter.py
curl -s localhost:8000/metrics

# Real API
BASE_URL=https://apigw-beta.huawei.com \
PROJECT_ID=... SERVICE_GROUP_ID=... REGION=cn-east-204-dev \
TOKEN=... python adapter.py
```

## Tests

```bash
cd aasp-metrics-adapter
python -m unittest tests.test_adapter -v
```

## Image

```bash
docker build -t <registry>/aasp-metrics-adapter:v0.2.0 .
docker push <registry>/aasp-metrics-adapter:v0.2.0
```

## Deploy with Kthena (demo)

1. Replace `<ADAPTER_IMAGE>` in `deploy.yaml`.
2. Apply (creates SA/RBAC + ModelServing + Policy/Binding).
3. Start with `MOCK=1`; confirm one pod has `aasp_adapter_is_leader 1`, others `0`.
4. Switch `MOCK=0`, set `BASE_URL` + `TOKEN` from Secret.

```bash
kubectl apply -f deploy.yaml
kubectl -n aasp-scale-demo get lease aasp-metrics-leader
kubectl -n aasp-scale-demo port-forward pod/<pod> 8000:8000
curl -s localhost:8000/metrics | grep aasp_
```

Binding scrapes all pods (`metricEndpoint` without `labelSelector`). Sum of predicted gauges across Ready pods ≈ global peak.

## Wire to autoscaling

Policy metric names must match gauges:

- `aasp_predicted_rpm`
- `aasp_predicted_prompt_tpm`
- `aasp_predicted_completion_tpm`

`targetValue` = per-instance capacity. Desired replicas ≈ max(metric / target) across the three series.
