# AASP → Kthena 预测扩缩容：可复现手册（含排障与切真 API）

> 环境：华为 CCE/HCS + `kthena-controller-manager:1.22.1`（Binding 仅支持 `metricEndpoint` 刮 Pod）  
> 链路：**AASP/MOCK → Adapter（Lease 选主）→ Pod `/metrics` → Binding 刮取 → 改 ModelServing.replicas**  
> 命名空间：`aasp-scale-demo`  
> 代码分支：`cursor/aasp-metrics-adapter-04c1`（目录 `aasp-metrics-adapter/`）  
> 本文以 **MOCK 闭环** 验证为主；文末说明如何切 **真实 AASP API**。

---

## 0. 架构说明（必读）

```text
AASP infer-recommendations（或 MOCK 环境变量）
        │
        ▼
ModelServing 每个副本都跑 Adapter
        │
        ├─ Lease 选主：仅 Leader 拉数并暴露非 0 的 aasp_predicted_*
        └─ Follower：不拉 AASP，预测指标报 0（避免 ×N）
        │
        ▼
AutoscalingPolicyBinding.metricEndpoint 刮全部 MS Pod（port 8000 /metrics）
        │
        ▼
Kthena Autoscaler 求和（= 全局峰值）→ 写 ModelServing.spec.replicas
```

**不要**再部署独立的 `Deployment/aasp-metrics-adapter` 与 ModelServing **共用**同一个 `LEASE_NAME`，否则 Leader 可能落在 Deployment 上，MS 全是 0，Autoscaler 扩不动。

独立 Deployment 仅适合调试；正式联调/验收时请删除，或设 `LEADER_ELECTION=0` 且换不同 `LEASE_NAME`。

---

## 1. 前置检查

```bash
# CRD
kubectl get crd | grep -iE 'autoscalingpolicy|autoscalingpolicybinding|modelserving'

# 控制器（可能有 2 个副本，日志要查对 Pod）
kubectl -n kube-system get deploy,pods | grep kthena

# Binding 是否只有 metricEndpoint（1.22.1）
kubectl explain autoscalingpolicybindings.spec.homogeneousTarget.target.metricEndpoint
```

控制器异常时（Lease 不刷新 / Pod 卡在坏节点）：

```bash
kubectl -n kube-system get lease | grep -i kthena
kubectl -n kube-system rollout restart deploy/kthena-controller-manager
# 若有坏节点：kubectl cordon <node>
```

准备镜像（示例，按你环境替换）：

```text
swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.3.0
```

镜像内须含 `adapter.py` + `leader_election.py`（选主版本）。

获取代码：

```bash
git clone -b cursor/aasp-metrics-adapter-04c1 https://github.com/Annie-Summer/Kthena.git
cd Kthena/aasp-metrics-adapter
```

---

## 2. 本地冒烟（可选）

```bash
cd aasp-metrics-adapter
PYTHONPATH=. python3 -m unittest tests.test_adapter -v

MOCK=1 MOCK_RPM=100 PROJECT_ID=p SERVICE_GROUP_ID=s REGION=cn-east-204-dev \
  LEADER_ELECTION=0 python3 adapter.py
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/metrics | grep aasp_
```

期望：`aasp_predicted_rpm ... 100`，`aasp_adapter_is_leader ... 1`（本地关选主时恒为 Leader）。

---

## 3. 构建并推送镜像

```bash
cd aasp-metrics-adapter
IMG=<你的仓库>/aasp-metrics-adapter:0.3.0   # 或更高版本
docker build -t "$IMG" .
docker push "$IMG"
```

无 Docker 时在其他机器 build，或使用已有 SWR 镜像。

---

## 4. 准备 deploy.yaml

1. 使用仓库中带选主的 `deploy.yaml`（必须能搜到关键字）：

```bash
grep -n 'LEADER_ELECTION\|ServiceAccount\|aasp-metrics-leader' deploy.yaml
# 必须有输出；若为空说明还是旧文件
```

2. 把所有 `<ADAPTER_IMAGE>` 换成真实镜像，**不要**留下占位符。

3. **建议删掉或注释掉** 独立 `Deployment` + `Service` 段，只保留：

   - Namespace  
   - ServiceAccount / Role / RoleBinding  
   - Secret（切真 API 时用）  
   - ModelServing  
   - AutoscalingPolicy / AutoscalingPolicyBinding  

若保留 Deployment：必须 `LEADER_ELECTION=0` 或 `LEASE_NAME` 与 MS 不同。

---

## 5. 一键部署（MOCK）

```bash
NS=aasp-scale-demo
kubectl apply -f deploy.yaml

# 确认 RBAC
kubectl -n $NS get sa,role,rolebinding | grep aasp

# 若仍存在会抢主的独立 Deployment，删掉：
kubectl -n $NS delete deploy aasp-metrics-adapter --ignore-not-found
kubectl -n $NS delete svc aasp-metrics-adapter --ignore-not-found

# 看 MS Pod
kubectl -n $NS get pods -w
# 期望：mock-predict-serving-0-infer-0-0  Running 1/1
```

ModelServing 关键 env 必须包含：

| 变量 | 值 |
|------|-----|
| `MOCK` | `1` |
| `MOCK_RPM` | `100`（基线） |
| `MOCK_PROMPT_TPM` / `MOCK_COMPLETION_TPM` | 如 `32000` |
| `LEADER_ELECTION` | `1` |
| `LEASE_NAME` | `aasp-metrics-leader` |
| `POD_NAME` / `POD_NAMESPACE` | downward API |
| `serviceAccountName` | `aasp-metrics-adapter` |

Binding：`metricEndpoint.port=8000`，`uri=/metrics`，**不要**再配 `labelSelector`（选主后刮全部即可）。  
Policy：`targetValue` rpm=100，prompt/completion_tpm=50000；`minReplicas=1`，`maxReplicas=6`。

---

## 6. 验收：选主 + 指标 + Autoscaler 基线

```bash
NS=aasp-scale-demo

# 6.1 Lease
kubectl -n $NS get lease aasp-metrics-leader -o yaml
kubectl -n $NS get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'
# 期望 holder = mock-predict-serving-...（不是已删除的 Deployment Pod）

# 6.2 Pod 指标
POD=$(kubectl -n $NS get pods -o name | grep mock-predict | head -1)
kubectl -n $NS port-forward $POD 18000:8000
# 另开终端：
curl -s http://127.0.0.1:18000/metrics | grep -E 'aasp_predicted_rpm|aasp_adapter_is_leader|aasp_adapter_up'
```

期望：

```text
aasp_predicted_rpm{...} 100.0
aasp_adapter_is_leader{...} 1
aasp_adapter_up{...} 1
```

```bash
# 6.3 Autoscaler 日志（先找到真正处理 Binding 的那个 controller Pod）
kubectl -n kube-system get pods | grep kthena-controller-manager
kubectl -n kube-system logs <controller-pod-B> --tail=50 | grep -E 'ReadyInstancesMetrics|recommendedInstances|connection refused'
```

期望类似：

```text
ReadyInstancesMetrics: [{"aasp_predicted_rpm":100,"aasp_predicted_prompt_tpm":32000,"aasp_predicted_completion_tpm":32000}]
recommendedInstances=1
```

```bash
kubectl -n $NS get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
# 期望 spec=1 status=1
```

---

## 7. 扩容测试（MOCK_RPM=100 → 600）

> **只改 MOCK_RPM 一项**，不要整段替换 env（会冲掉 `POD_NAME` / `LEADER_ELECTION`）。  
> 按 `deploy.yaml` / 本文 MS 的 env 顺序：下标 `1` = `MOCK_RPM`。

```bash
NS=aasp-scale-demo
kubectl -n $NS patch modelserving mock-predict-serving --type=json -p='[
  {"op":"replace","path":"/spec/template/roles/0/entryTemplate/spec/containers/0/env/1/value","value":"600"}
]'

# 重建 Pod 使 env 生效
kubectl -n $NS get pods -o name | grep mock-predict | xargs -r kubectl -n $NS delete
kubectl -n $NS get pods -w
```

等待约 30～90 秒后：

```bash
kubectl -n kube-system logs <controller-pod-B> --tail=20 | grep ReadyInstancesMetrics
# 期望 rpm=600（不是 3600）

kubectl -n $NS get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
# 期望 spec=6 status=6

kubectl -n $NS get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'
kubectl -n $NS get pods | grep mock-predict
```

计算公式：`desired ≈ max(600/100, 32000/50000, 32000/50000) = 6`。

多副本时抽查：

```bash
for p in $(kubectl -n $NS get pods -o name | grep mock-predict); do
  echo "=== $p ==="
  kubectl -n $NS exec ${p#pod/} -- wget -qO- http://127.0.0.1:8000/metrics 2>/dev/null \
    | grep -E 'aasp_adapter_is_leader|aasp_predicted_rpm' || \
  kubectl -n $NS exec ${p#pod/} -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())" \
    | grep -E 'aasp_adapter_is_leader|aasp_predicted_rpm'
done
# 仅一个 is_leader=1 且 rpm=600；其余 is_leader=0 且 rpm=0
```

---

## 8. 缩容测试（MOCK_RPM=600 → 10）

```bash
NS=aasp-scale-demo
kubectl -n $NS patch modelserving mock-predict-serving --type=json -p='[
  {"op":"replace","path":"/spec/template/roles/0/entryTemplate/spec/containers/0/env/1/value","value":"10"}
]'
kubectl -n $NS get pods -o name | grep mock-predict | xargs -r kubectl -n $NS delete
```

缩容受 `scaleDown.stabilizationWindow` / `percent` 限制，会 **逐步** 降（如 6→3→2→1），通常 1～3 分钟：

```bash
watch -n 5 "kubectl -n $NS get modelserving mock-predict-serving -o jsonpath='spec={.spec.replicas} status={.status.replicas}{\"\\n\"}'; kubectl -n $NS get pods | grep mock-predict"
```

最终期望：

```text
spec=1 status=1
ReadyInstancesMetrics.rpm=10
lease holder = mock-predict-serving-0-infer-0-0（或当前唯一 Pod）
```

---

## 9. MOCK 验收清单

| # | 检查项 | 通过标准 |
|---|--------|----------|
| 1 | `deploy.yaml` 含选主字段 | `grep LEADER_ELECTION` 有输出 |
| 2 | 镜像非占位符 | 不是 `<ADAPTER_IMAGE>` |
| 3 | 无抢主 Deployment | `get deploy aasp-metrics-adapter` NotFound 或 LEADER_ELECTION=0 |
| 4 | Lease | holder 为 MS Pod |
| 5 | `/metrics` | Leader：`rpm` 与 MOCK 一致，`is_leader=1` |
| 6 | 基线 | rpm=100 → replicas=1 |
| 7 | 扩容 | rpm=600 → replicas=6，且日志 rpm=600 非 3600 |
| 8 | 缩容 | rpm=10 → replicas=1 |

全部通过即证明：在 1.22.1（仅 Pod scrape）下，**选主 Adapter + Binding** 可驱动预测扩缩容。

---

## 10. 排障手册（按症状）

### 10.1 `get lease` NotFound

```bash
grep LEADER_ELECTION deploy.yaml          # 空 → 旧 YAML
kubectl -n aasp-scale-demo get sa,role    # 无 aasp → 未 apply RBAC
kubectl -n aasp-scale-demo logs <ms-pod> --tail=50
# 缺 POD_NAME/POD_NAMESPACE 会直接退出选主
kubectl -n aasp-scale-demo exec <ms-pod> -- env | grep -E 'LEADER|POD_'
```

### 10.2 Lease holder 是 Deployment Pod / MS 指标全 0

```bash
kubectl -n aasp-scale-demo get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'
kubectl -n aasp-scale-demo delete deploy aasp-metrics-adapter --ignore-not-found
kubectl -n aasp-scale-demo delete pod -l app=aasp-metrics-adapter --ignore-not-found
kubectl -n aasp-scale-demo get pods -o name | grep mock-predict | xargs kubectl -n aasp-scale-demo delete
```

Autoscaler 日志会出现 `ReadyInstancesMetrics: rpm=0`。

### 10.3 `connection refused` 刮 :8000

Pod 刚创建 / 进程未监听。等 Ready 后再看；持续失败则：

```bash
kubectl -n aasp-scale-demo describe pod <ms-pod>
kubectl -n aasp-scale-demo logs <ms-pod>
kubectl -n aasp-scale-demo exec <ms-pod> -- cat /proc/1/cmdline
```

镜像若仍是旧的、或 `Permission denied`，需换可读镜像 / `runAsUser: 0`。

### 10.4 日志里没有 ReadyInstancesMetrics

控制器有 **两个** Pod，处理 Binding 的往往是其中一个：

```bash
kubectl -n kube-system get pods | grep kthena-controller-manager
kubectl -n kube-system logs <pod-A> --tail=100 | grep -i binding
kubectl -n kube-system logs <pod-B> --tail=100 | grep -i ReadyInstances
```

### 10.5 `ReadyInstancesMetrics: [{}]` 或缺字段

- Binding 端口不是 **8000**  
- Policy 指标名与 gauge 不一致（须为 `aasp_predicted_rpm` 等）  
- 刮到了但解析失败  

```bash
kubectl -n aasp-scale-demo get autoscalingpolicybinding aasp-predictive-binding-multi -o yaml | grep -A5 metricEndpoint
kubectl -n aasp-scale-demo get autoscalingpolicy aasp-predictive-scaling-multi -o yaml | grep -A20 metrics
```

### 10.6 扩到 6 但日志 rpm=3600（×N）

选主未生效：所有 Pod 都在报真实全局值。检查：

```bash
kubectl -n aasp-scale-demo exec <pod> -- env | grep LEADER_ELECTION
# 各 Pod 的 aasp_adapter_is_leader
```

确认镜像含 `leader_election.py`，且 `LEADER_ELECTION=1`。

### 10.7 改了 MOCK 指标不变

必须删 Pod 重建；仅 patch ModelServing 不会热更新已跑进程的环境变量。

### 10.8 patch env 后选主坏了

整段替换 `env` 冲掉了 `POD_NAME` fieldRef。只用 json patch 改单个 value（见 §7），或重新 apply 完整 MS YAML。

### 10.9 `spec` 降了但 `status`/Pod 数滞后

缩容是渐进的；`status` 可能短暂不一致。以 `spec.replicas` + 实际 Running Pod 数 + 日志 `recommendedInstances` 为准。

---

## 11. 下一步：切换真实 AASP API

MOCK 闭环通过后，把数据源从环境变量改为 AASP HTTP API。

### 11.1 API 约定

两种路径（由环境变量选择）：

```text
# 旧/网关形态（Bearer）
GET {BASE_URL}/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations?...
Authorization: Bearer {TOKEN}

# 实验室/instance 形态（与下列 curl 一致）
GET {BASE_URL}/v1/{PROJECT_ID}/instance/{INSTANCE_ID}/infer-recommendations
    ?region=...&start_time=...&end_time=...
X-Auth-Token: {TOKEN}
```

对应 curl 示例：

```bash
curl -kv -H "X-Auth-Token: <token>" \
  "http://100.94.170.238:8088/v1/<PROJECT_ID>/instance/<INSTANCE_ID>/infer-recommendations?start_time=...&end_time=...&region=cn-north-5"
```

Adapter 环境变量映射：

| curl / API | Adapter env |
|------------|-------------|
| `http://100.94.170.238:8088` | `BASE_URL` |
| path 中 project id | `PROJECT_ID` |
| path 中 instance uuid | `INSTANCE_ID` |
| `region=` | `REGION` |
| `X-Auth-Token` | `AUTH_HEADER=x-auth-token` + `TOKEN` |
| 时间窗 | `TIME_RANGE_MODE=backward` + `WINDOW_MINUTES`（滚动窗口；不必手写绝对时间） |

Adapter 对 `resources.predictions[]` 取窗口 **max**（rpm / prompt_tpm / completion_tpm）。

须使用包含 `INSTANCE_ID` / `AUTH_HEADER` 支持的镜像（重新 build 推送，勿继续用仅 Bearer 旧镜像）。

### 11.2 写入 Secret

```bash
NS=aasp-scale-demo
kubectl -n $NS create secret generic aasp-api-token \
  --from-literal=token='<你的 Bearer Token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 11.3 改 ModelServing 环境变量

在 MS 容器 env 中设置（保留选主相关变量）：

| 变量 | 值 |
|------|-----|
| `MOCK` | `0` |
| `BASE_URL` | `https://apigw-beta.huawei.com`（或生产） |
| `PROJECT_ID` | 真实 project id |
| `SERVICE_GROUP_ID` | 真实预测单元 id |
| `REGION` | 如 `cn-east-204-dev` |
| `TOKEN` | `secretKeyRef: aasp-api-token / token` |
| `WINDOW_MINUTES` | 默认 `5` |
| `POLL_SECONDS` | 默认 `15` |
| `LEADER_ELECTION` | `1`（保持） |
| `POD_NAME` / `POD_NAMESPACE` | 保持 downward API |

删除或忽略 `MOCK_RPM` 等（`MOCK=0` 时不用）。

示例片段：

```yaml
env:
  - name: MOCK
    value: "0"
  - name: BASE_URL
    value: "https://apigw-beta.huawei.com"
  - name: PROJECT_ID
    value: "<project_id>"
  - name: SERVICE_GROUP_ID
    value: "<service_group_id>"
  - name: REGION
    value: "<region>"
  - name: TOKEN
    valueFrom:
      secretKeyRef:
        name: aasp-api-token
        key: token
  - name: LEADER_ELECTION
    value: "1"
  - name: LEASE_NAME
    value: "aasp-metrics-leader"
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
```

集群内 Pod 须能访问 `BASE_URL`（出网 / 代理 / 安全组按环境放开）。

### 11.4 重建并验证

```bash
NS=aasp-scale-demo
kubectl -n $NS get pods -o name | grep mock-predict | xargs -r kubectl -n $NS delete

kubectl -n $NS logs <ms-pod> --tail=50
# 期望：updated peaks rpm=... 或明确的 HTTP 错误（便于排障）
# 不应再出现 mock peaks

kubectl -n $NS port-forward pod/<ms-pod> 18000:8000
curl -s localhost:18000/metrics | grep aasp_predicted_rpm
```

`aasp_adapter_up=0` 且保留上次值 → 拉 AASP 失败，看日志里的 HTTP/TOKEN/空 predictions。

### 11.5 校准 targetValue

真实峰值与 MOCK 不同，按单实例容量调整 Policy：

```text
desired ≈ max(
  aasp_predicted_rpm / target_rpm,
  aasp_predicted_prompt_tpm / target_prompt_tpm,
  aasp_predicted_completion_tpm / target_completion_tpm
)
```

先用较小 `maxReplicas` 观察，再放开。

### 11.6 真 API 验收

| 检查 | 标准 |
|------|------|
| 日志 | `updated peaks` 来自 API，非 mock |
| `/metrics` | 数值随 AASP 窗口变化 |
| `aasp_adapter_up` | 多数时间为 1 |
| 仅 Leader 拉 API | Follower 日志有 `skip AASP poll`；AASP QPS ≈ `1/POLL_SECONDS` |
| 扩缩 | 峰值升高/降低时 replicas 同向变化且无 ×N |

---

## 12. 常用命令速查

```bash
NS=aasp-scale-demo

kubectl -n $NS get modelserving,autoscalingpolicy,autoscalingpolicybinding,lease,pods
kubectl -n $NS get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'
kubectl -n $NS get modelserving mock-predict-serving -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'

# 找 Autoscaler 日志
kubectl -n kube-system get pods | grep kthena-controller-manager
kubectl -n kube-system logs <pod> --tail=100 | grep -E 'ReadyInstancesMetrics|recommendedInstances|connection refused'

# 清环境（慎用）
# kubectl delete ns aasp-scale-demo
```

---

## 13. 已知限制（1.22.1）

- 无 Prometheus/AOM 直查；指标必须出现在 ModelServing Pod `/metrics`。  
- 选主依赖 `coordination.k8s.io/Lease` + RBAC。  
- Leader 切换有约 `LEASE_DURATION_SECONDS`（默认 15s）空窗，期间可能短暂采到 0。  
- 升级到社区 1.0.0 类 API（`metricSources.prometheus`）后，可改为 AASP→（可选 Adapter）→Prometheus/AOM→Kthena PromQL，无需 Pod 选主。
