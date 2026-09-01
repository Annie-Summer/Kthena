# AASP Metrics Adapter

Polls Huawei AASP `infer-recommendations` API, takes **max** over prediction points, and exposes Prometheus gauges for Kthena Autoscaler (`metricEndpoint` Pod scrape).

**Design (architecture, leader election rationale, Kthena scaling):** see [DESIGN.md](./DESIGN.md).  
**deploy.yaml resource-by-resource:** see [DEPLOY.md](./DEPLOY.md).  
**Token manual vs IAM auto re-login:** see [TOKEN-MODES.md](./TOKEN-MODES.md).

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
| `TOKEN` | yes* | | initial token (manual mode; also seed for auto mode) |
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
| `IAM_AUTH_URL` | for auto | Huawei IAM tokens URL | `…/v3/auth/tokens?nocatalog=true` |
| `IAM_USER` / `IAM_PASSWORD` / `IAM_DOMAIN` | for auto | | password login |
| `IAM_PROJECT_NAME` or `IAM_PROJECT_ID` | for auto | | token scope |
| `IAM_REFRESH_SKEW_SECONDS` | no | `300` | refresh if expiry within N seconds |

\* Not required when `MOCK=1`. With IAM auto-refresh configured, `TOKEN` may be empty (Adapter will login), but seeding an initial token is still fine.

## Token modes

详见专文：**[TOKEN-MODES.md](./TOKEN-MODES.md)**（手动填写 vs IAM 自动重登的步骤与对照）。

1. **Manual only:** set `TOKEN` (Secret). On expiry, update Secret and recreate pods.  
2. **Auto re-login (optional):** also set `IAM_*`. On AASP **401/403**, Adapter calls IAM, stores new token **in memory**, retries once (no pod restart). Also refreshes when `expires_at` is within `IAM_REFRESH_SKEW_SECONDS`.

```bash
# Auto mode example (do not commit real passwords)
AUTH_HEADER=x-auth-token \
IAM_AUTH_URL='https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true' \
IAM_DOMAIN=... IAM_USER=... IAM_PASSWORD=... IAM_PROJECT_NAME=cn-north-5 \
BASE_URL=... PROJECT_ID=... INSTANCE_ID=... REGION=cn-north-5 \
python adapter.py
```

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

**完整可复现步骤：**

- MOCK 联调 / 排障：见 [TEST-GUIDE.md](./TEST-GUIDE.md)
- **真 AASP 实际场景测试：见 [REAL-SCENARIO-TEST-GUIDE.md](./REAL-SCENARIO-TEST-GUIDE.md)**

1. Replace image in `deploy.yaml` with a build that supports `INSTANCE_ID` + `AUTH_HEADER=x-auth-token` (e.g. `0.4.0+`).
2. Prefer **only ModelServing** for scaling; do not deploy a standalone adapter Deployment on the same Lease.
3. Apply SA/RBAC + MS + Policy/Binding; confirm Lease holder is an MS pod.
4. For real API: `MOCK=0`, `BASE_URL`, `INSTANCE_ID`, `AUTH_HEADER=x-auth-token`, Secret token; then follow REAL-SCENARIO-TEST-GUIDE.md.

## Wire to autoscaling

Policy metric names must match gauges:

- `aasp_predicted_rpm`
- `aasp_predicted_prompt_tpm`
- `aasp_predicted_completion_tpm`

`targetValue` = per-instance capacity. Desired replicas ≈ max(metric / target) across the three series.
