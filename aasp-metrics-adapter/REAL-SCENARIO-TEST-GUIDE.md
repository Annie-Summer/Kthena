# 实际场景测试流程：AASP 真 API → Adapter（选主）→ Kthena 扩缩容

> 适用：华为 CCE/HCS + `kthena-controller-manager:1.22.1`（**不**升级社区 1.0.0）  
> 链路：`AASP API → ModelServing 内 Adapter（Lease 选主）→ Binding 刮 /metrics → 改 ModelServing.spec.replicas`  
> 命名空间：`aasp-scale-demo`  
> 代码分支：`cursor/aasp-metrics-adapter-04c1`（需含 `INSTANCE_ID` + `AUTH_HEADER=x-auth-token` 的镜像）

本文可独立复现；排障可对照 `TEST-GUIDE.md` §10。

---

## 0. 架构与约束（先读）

```text
真实 AASP
  GET http://<AASP_HOST>:8086/v1/<PROJECT_ID>/instance/<INSTANCE_ID>/infer-recommendations
  Header: X-Auth-Token: <token>
        │
        ▼  仅 Leader 轮询
ModelServing 各副本跑同一 Adapter 镜像
  Leader：暴露真实 aasp_predicted_*
  Follower：暴露 0（避免 ×N）
        │
        ▼
AutoscalingPolicyBinding.metricEndpoint 刮全部 MS Pod :8000/metrics
        │
        ▼
kthena-controller-manager 汇总 → 写 ModelServing.spec.replicas
```

硬约束：

1. **不要**再部署独立 `Deployment/aasp-metrics-adapter`（会抢同一 Lease）。  
2. 继续用 1.22.1 的 Policy + Binding + `metricEndpoint`，不用 Prometheus `metricSources`。  
3. 集群内 Pod 必须能访问 AASP 地址（如 `100.94.170.238:8086`）。  
4. 镜像必须是支持 lab 响应解析的新构建（建议 **`0.4.1+`**：`prediction` map + `prompt_token`；`0.4.0` 不够）。

---

## 1. 前置检查

```bash
NS=aasp-scale-demo

# CRD
kubectl get crd | grep -iE 'autoscalingpolic|modelserving'

# 控制器及 Lease（RENEW 应接近当前时间）
kubectl -n kube-system get deploy,pods | grep kthena
kubectl -n kube-system get lease lease.kthena.controller-manager \
  -o custom-columns=HOLDER:.spec.holderIdentity,RENEW:.spec.renewTime
```

若 `RENEW` 过期数天：

```bash
kubectl -n kube-system rollout restart deploy/kthena-controller-manager
kubectl -n kube-system rollout status deploy/kthena-controller-manager
```

### 1.1 节点上先打通真 API（最近 10 分钟）

```bash
# 设置 token（勿提交到 git）
export token='<你的 X-Auth-Token>'

END=$(date +%Y-%m-%dT%H:%M:%S)
START=$(date -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S)
# 若 date -d 不可用（部分系统）：用 python/手动算时间

echo "START=$START END=$END"

curl -kv -H "X-Auth-Token: $token" \
  "http://100.94.170.238:8086/v1/5dfed145e29a43f7b42c5ecc17d4d98c/instance/922ae983-addb-46e8-8096-5092de62af13/infer-recommendations?start_time=${START}&end_time=${END}&region=cn-north-5"
```

**通过标准：** HTTP 200，body 含预测点（例如 `resources.<group>.prediction[]`，字段可能是 `rpm` / `prompt_token` / `completion_token`；旧文档也可能是 `predictions` + `*_tpm`）。Adapter `0.4.1+` 两种形状都支持，并对各 group 取 max。  
此步失败则先别部署 Adapter。

记录你将使用的常量：

| 项 | 示例值 |
|----|--------|
| BASE_URL | `http://100.94.170.238:8086` |
| PROJECT_ID | `5dfed145e29a43f7b42c5ecc17d4d98c` |
| INSTANCE_ID | `922ae983-addb-46e8-8096-5092de62af13` |
| REGION | `cn-north-5` |
| AUTH | `X-Auth-Token` |

---

## 2. 准备代码与镜像

```bash
git clone -b cursor/aasp-metrics-adapter-04c1 https://github.com/Annie-Summer/Kthena.git
cd Kthena/aasp-metrics-adapter

# 确认能力
grep -n 'INSTANCE_ID\|AUTH_HEADER\|x-auth-token' adapter.py

IMG=swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.4.1
docker build -t "$IMG" .
docker push "$IMG"
```

本地单测（可选）：

```bash
PYTHONPATH=. python3 -m unittest tests.test_adapter -v
```

---

## 3. 清空旧 demo（可选，适合从零）

```bash
kubectl delete namespace aasp-scale-demo --ignore-not-found
# 等到 NotFound
kubectl get ns aasp-scale-demo
```

---

## 4. 部署基础资源 + ModelServing（真 API）

### 4.1 准备 `deploy.yaml`

使用仓库中 **无独立 Deployment/Service** 的版本。将 ModelServing 容器改为：

- `image: .../aasp-metrics-adapter:0.4.1`
- `MOCK=0` + 真 API 环境变量（见下）

完整 ModelServing 示例（其余 Namespace/SA/Role/RoleBinding/Policy/Binding 与仓库 `deploy.yaml` 相同）：

```yaml
apiVersion: workload.serving.volcano.sh/v1alpha1
kind: ModelServing
metadata:
  name: mock-predict-serving
  namespace: aasp-scale-demo
spec:
  replicas: 1
  recoveryPolicy: None
  template:
    roles:
      - name: infer
        replicas: 1
        workerReplicas: 0
        entryTemplate:
          spec:
            serviceAccountName: aasp-metrics-adapter
            containers:
              - name: adapter
                image: swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.4.1
                imagePullPolicy: Always
                ports:
                  - name: metrics
                    containerPort: 8000
                env:
                  - name: MOCK
                    value: "0"
                  - name: BASE_URL
                    value: "http://100.94.170.238:8086"
                  - name: PROJECT_ID
                    value: "5dfed145e29a43f7b42c5ecc17d4d98c"
                  - name: INSTANCE_ID
                    value: "922ae983-addb-46e8-8096-5092de62af13"
                  - name: REGION
                    value: "cn-north-5"
                  - name: AUTH_HEADER
                    value: "x-auth-token"
                  - name: TIME_RANGE_MODE
                    value: "backward"
                  - name: WINDOW_MINUTES
                    value: "10"
                  - name: POLL_SECONDS
                    value: "15"
                  - name: METRICS_PORT
                    value: "8000"
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
                resources:
                  requests:
                    cpu: 50m
                    memory: 64Mi
                  limits:
                    cpu: 200m
                    memory: 128Mi
            imagePullSecrets:
              - name: default-secret
```

Policy/Binding 建议先沿用 MOCK 联调值（可按真峰值再调）：

- 指标：`aasp_predicted_rpm` / `prompt_tpm` / `completion_tpm`
- `targetValue`：如 rpm=`100`，tpm=`50000`
- Binding：`minReplicas=1`，`maxReplicas=6`（或按业务调大），`metricEndpoint.port=8000`，`uri=/metrics`
- **无** `labelSelector`（靠选主避免 ×N）

### 4.2 写入 Secret 并 apply

```bash
NS=aasp-scale-demo

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" create secret generic aasp-api-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f deploy.yaml
# 若 Secret 在 deploy.yaml 里仍是 replace-me，务必用上面命令覆盖

# 确认没有独立 Deployment
kubectl -n "$NS" get deploy
# 期望：No resources found
```

### 4.3 等待 Pod Ready

```bash
kubectl -n "$NS" get sa,role,rolebinding,secret,modelserving,autoscalingpolicy,autoscalingpolicybinding,pods,lease
kubectl -n "$NS" get pods -w
# Ctrl+C 结束 watch
```

期望：`mock-predict-serving-0-infer-0-0` 为 `1/1 Running`。

---

## 5. 验收清单（真 API）

全程保持：`NS=aasp-scale-demo`。

### 5.1 RBAC

```bash
kubectl -n "$NS" get sa,role,rolebinding | grep aasp
```

### 5.2 Adapter 选主 Lease

```bash
kubectl -n "$NS" get lease aasp-metrics-leader -o yaml
kubectl -n "$NS" get lease aasp-metrics-leader \
  -o jsonpath='{.spec.holderIdentity}{"\n"}'
```

期望：holder = `mock-predict-serving-...`。

### 5.3 Pod 内能访问 AASP（网络）

```bash
POD=$(kubectl -n "$NS" get pods -o name | grep mock-predict | head -1 | sed 's|pod/||')
kubectl -n "$NS" exec "$POD" -- env | grep -E 'MOCK|BASE_URL|INSTANCE_ID|AUTH_HEADER|WINDOW|TOKEN'
# TOKEN 有值即可，不要把 token 打到共享日志里

kubectl -n "$NS" logs "$POD" --tail=50
```

期望日志：

- 有 `updated peaks rpm=...`（**不是** `mock peaks`）
- 无持续 `HTTP 401/403`、`connection refused`、`empty predictions`

失败时对照：

| 日志 | 处理 |
|------|------|
| `TOKEN is empty` | Secret / secretKeyRef |
| `HTTP 401/403` | Token 无效或过期 |
| `URLError` / timed out | 网络到 `100.94.170.238:8086` |
| `empty predictions` | 响应结构不匹配或时间窗无数据；确认是 `prediction`/`predictions`；加大 `WINDOW_MINUTES` |
| `forbidden` leases | SA/Role 缺失 |

### 5.4 `/metrics` 内容

```bash
kubectl -n "$NS" port-forward pod/"$POD" 18000:8000
# 另开终端：
curl -s http://127.0.0.1:18000/metrics | grep -E 'aasp_predicted_rpm|aasp_adapter_is_leader|aasp_adapter_up'
```

期望：

```text
aasp_predicted_rpm{...} <真实数值>
aasp_adapter_is_leader{...} 1
aasp_adapter_up{...} 1
```

### 5.5 Kthena 采到并给出推荐副本

```bash
HOLDER=$(kubectl -n kube-system get lease lease.kthena.controller-manager -o jsonpath='{.spec.holderIdentity}')
CPOD=${HOLDER%%_*}
echo "controller=$CPOD"

kubectl -n kube-system logs "$CPOD" --tail=30 \
  | grep -E 'ReadyInstancesMetrics|recommendedInstances|successfully update|connection refused'
```

期望：`ReadyInstancesMetrics` 含非空数值（不是 `[{}]`），且与 `/metrics` 同量级；有 `successfully update target replicas`。

```bash
kubectl -n "$NS" get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
```

粗算：

```text
desired ≈ max(
  rpm / target_rpm,
  prompt_tpm / target_prompt_tpm,
  completion_tpm / target_completion_tpm
)
限制在 [minReplicas, maxReplicas]
```

---

## 6. 扩缩行为观察（真数据）

真 API 不能像 MOCK 那样改 `MOCK_RPM`，观察方式：

### 6.1 对照人工 curl 与 Adapter

同一时刻对比节点 curl（最近 10 分钟 max）与 Pod `/metrics` 是否接近。

### 6.2 调 `targetValue` 做受控扩缩（推荐联调手法）

在预测值相对稳定时：

1. 记下当前 `rpm`（如 300）  
2. 把 Policy 里 `aasp_predicted_rpm` 的 `targetValue` 改成很小（如 `50`）→ 期望副本上升  
3. 再改回合理值（如 `300` 或更大）→ 期望回落  

```bash
kubectl -n "$NS" edit autoscalingpolicy aasp-predictive-scaling-multi
# 或 kubectl patch ...

# 观察（缩容有稳定窗口，可能需 1～3 分钟）
kubectl -n "$NS" get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
kubectl -n kube-system logs "$CPOD" --tail=20 | grep ReadyInstancesMetrics
```

### 6.3 多副本时验证无 ×N

当 `replicas>1`：

```bash
kubectl -n "$NS" get pods | grep mock-predict
kubectl -n "$NS" get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'

# 抽查：仅 Leader is_leader=1 且 rpm 非 0；其余为 0
```

控制器日志中的 `ReadyInstancesMetrics.rpm` 应约等于 **单个 Leader 的值**，而不是 `N × 该值`。

### 6.4 Leader 被删后的故障转移

```bash
LEADER=$(kubectl -n "$NS" get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}')
kubectl -n "$NS" delete pod "$LEADER"
# 约 15s 内
kubectl -n "$NS" get lease aasp-metrics-leader -o jsonpath='{.spec.holderIdentity}{"\n"}'
```

期望：新 holder 为其它（或重建后的）MS Pod；短暂可能 `[{}]` 或 0，随后恢复。

---

## 7. 实际场景验收表

| # | 检查项 | 通过标准 |
|---|--------|----------|
| 1 | 节点 curl 最近 10 分钟 | 200 + predictions 有数 |
| 2 | 镜像 | `0.4.1+`，含 lab `prediction` map 与 `prompt_token` 解析 |
| 3 | 无独立 Deployment | `get deploy` 为空 |
| 4 | RBAC | sa/role/rolebinding 存在 |
| 5 | Adapter Lease | holder 为 MS Pod |
| 6 | Adapter 日志 | `updated peaks`，非 mock |
| 7 | `/metrics` | `is_leader=1`，`up=1`，rpm 为真值 |
| 8 | Controller Lease | RENEW 新鲜 |
| 9 | ReadyInstancesMetrics | 非 `[{}]`，与指标一致 |
| 10 | 无 ×N | 多副本时汇总 ≈ Leader 单值 |
| 11 | 改 targetValue | replicas 同向变化 |
| 12 | 删 Leader | Lease 转移，指标恢复 |

---

## 8. 常见问题速查

| 现象 | 处理 |
|------|------|
| `get lease aasp-metrics-leader` NotFound 且查到 default ns | 先 `NS=aasp-scale-demo` |
| ReadyInstancesMetrics `[{}]` | 查控制器 Lease 是否僵死；重启 controller；确认 MS `/metrics` 有数 |
| 两 controller 都有日志 | 以 `lease.kthena.controller-manager` 的 holder（下划线前）为准 |
| rpm 正常但不扩 | 查 `targetValue`、`maxReplicas`、tolerance、scaleUp 窗口 |
| Token 写进 yaml 明文 | 改用 Secret + `secretKeyRef` |
| 时间写错 `2026-08-317` | 必须是合法日期；滚动窗交给 Adapter 的 `WINDOW_MINUTES` |

---

## 9. 生产形态提示（测通后）

联调通过后，将 Adapter 改为推理 Pod 的 **sidecar**（主容器跑 vLLM 等，Adapter 换端口如 8001，Binding `port` 同步）。  
选主、真 API、Policy/Binding 逻辑不变。

---

## 10. 一键命令摘要

```bash
export NS=aasp-scale-demo
export token='<X-Auth-Token>'

# 人工最近 10 分钟
END=$(date +%Y-%m-%dT%H:%M:%S); START=$(date -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S)
curl -sS -H "X-Auth-Token: $token" \
  "http://100.94.170.238:8086/v1/5dfed145e29a43f7b42c5ecc17d4d98c/instance/922ae983-addb-46e8-8096-5092de62af13/infer-recommendations?start_time=${START}&end_time=${END}&region=cn-north-5" | head

# 集群状态
kubectl -n "$NS" get pods,lease,modelserving
POD=$(kubectl -n "$NS" get pods -o name | grep mock-predict | head -1 | sed 's|pod/||')
kubectl -n "$NS" logs "$POD" --tail=30

HOLDER=$(kubectl -n kube-system get lease lease.kthena.controller-manager -o jsonpath='{.spec.holderIdentity}')
kubectl -n kube-system logs "${HOLDER%%_*}" --tail=20 | grep ReadyInstancesMetrics
```

按 §1→§7 顺序执行即可完成「真 AASP → Kthena 扩缩」实际场景验收。
