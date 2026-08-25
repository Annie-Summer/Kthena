# AASP Metrics Adapter

Polls Huawei AASP `infer-recommendations` API, takes **max** over `resources.predictions`, and exposes Prometheus gauges for Kthena Autoscaler (`metricEndpoint` Pod scrape).

## Metrics

| Metric | Source |
|--------|--------|
| `aasp_predicted_rpm` | `max(predictions[].rpm)` |
| `aasp_predicted_prompt_tpm` | `max(predictions[].prompt_tpm)` |
| `aasp_predicted_completion_tpm` | `max(predictions[].completion_tpm)` |
| `aasp_predicted_total_tpm` | `max(predictions[].total_tpm)` (optional) |
| `aasp_predicted_latency_ms` | `max(predictions[].latency)` (optional) |
| `aasp_adapter_up` | `1` if last fetch OK |

On fetch failure the adapter **keeps the last good values** and sets `aasp_adapter_up=0`.

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

\* Not required when `MOCK=1`.

## Local run

```bash
cd aasp-metrics-adapter

# Offline demo
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
docker build -t <registry>/aasp-metrics-adapter:v0.1.0 .
docker push <registry>/aasp-metrics-adapter:v0.1.0
```

## Deploy with Kthena (demo)

1. Replace `<ADAPTER_IMAGE>` in `deploy.yaml`.
2. Start with `MOCK=1`, confirm gauges and replica changes by editing Deployment/ModelServing env (`MOCK_RPM` etc.) and rolling pods.
3. Switch `MOCK=0`, set `BASE_URL` + `TOKEN` from Secret.

```bash
kubectl apply -f deploy.yaml
kubectl -n aasp-scale-demo port-forward deploy/aasp-metrics-adapter 8000:8000
curl -s localhost:8000/metrics
```

## Recommended: Scheme A (single scrape pod)

Global AASP peaks must be scraped from **one** ModelServing pod. Otherwise Kthena sums the same value across replicas and over-scales (×N).

1. Run Adapter (sidecar or container) on the ModelServing you scale; expose `:8000/metrics`.
2. Mark **exactly one** Ready pod:

```bash
kubectl -n <ns> label pod <one-pod> aasp-metric-source=true --overwrite
# when that pod is gone, label another Ready pod the same way
```

3. Binding scrapes only that pod (`deploy.yaml` already sets this):

```yaml
metricEndpoint:
  port: 8000
  uri: /metrics
  labelSelector:
    matchLabels:
      aasp-metric-source: "true"
```

4. Confirm on your cluster that `metricEndpoint.labelSelector` exists:

```bash
kubectl explain autoscalingpolicybindings.spec.homogeneousTarget.target.metricEndpoint
```

If your 1.22.1 build has no `labelSelector`, fall back to: only the elected pod exposes non-zero gauges; all other pods expose `0` for the three predicted series (sum still equals the global peak).

## Wire to autoscaling

Policy metric names must match gauges:

- `aasp_predicted_rpm`
- `aasp_predicted_prompt_tpm`
- `aasp_predicted_completion_tpm`

`targetValue` = per-instance capacity. Desired replicas ≈ max(metric / target) across the three series.
