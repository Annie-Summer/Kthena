# AASP Metrics Adapter + Kthena 预测扩缩容测试手册（可复现）

> 环境：华为 CCE + Kthena（AutoscalingPolicy / Binding / ModelServing）  
> 目标：用 MOCK 指标验证「Adapter → 三指标 → Autoscaler → ModelServing 副本」闭环  
> 命名空间：`aasp-scale-demo`

---

## 0. 前置条件

- 集群已安装 CRD：
  - `autoscalingpolicies.workload.serving.volcano.sh`
  - `autoscalingpolicybindings.workload.serving.volcano.sh`
  - `modelservings.workload.serving.volcano.sh`
- `kthena-controller-manager` 可运行（避免调度到异常节点）
- 已有 Adapter 镜像（示例）：
  - `swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.2.0`
- 本机可执行 `kubectl`；有 Python3 时可先做本地冒烟
- 代码目录：`aasp-metrics-adapter/`（含 `adapter.py`、`Dockerfile`、`deploy.yaml`）

检查 CRD / 控制器：

```bash
kubectl get crd | grep -iE 'autoscaling|modelserving|kthena'
kubectl -n kube-system get deploy kthena-controller-manager
kubectl -n kube-system get pods -o wide | grep kthena
```

若控制器 Lease 长时间不刷新，或 Pod 落在坏节点（如 `135.0.0.49` 出现 `runtimeTimeout` / `ContainerCreating`）：

```bash
kubectl cordon 135.0.0.49   # 按实际坏节点名调整
kubectl -n kube-system scale deploy kthena-controller-manager --replicas=1
kubectl -n kube-system rollout restart deploy/kthena-controller-manager
kubectl -n kube-system rollout status deploy/kthena-controller-manager
kubectl -n kube-system get lease lease.kthena.controller-manager \
  -o jsonpath='{.spec.holderIdentity} {.spec.renewTime}{"\n"}'
```

---

## 1. 本地冒烟（可选）

```bash
cd aasp-metrics-adapter

# 单测
PYTHONPATH=. python3 -m unittest tests.test_adapter -v

# 启动 MOCK Adapter
MOCK=1 PROJECT_ID=p SERVICE_GROUP_ID=s REGION=cn-east-204-dev python3 adapter.py
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/metrics
```

期望包含：

```text
aasp_predicted_rpm{...} 100.0
aasp_adapter_up{...} 1
```

验证完在跑 `adapter.py` 的终端按 `Ctrl+C` 结束。

---

## 2. 构建镜像（有 Docker 的机器）

> 无 Docker、仅有 `crictl` 时：在其他机器 build/push，或使用已推到 SWR 的镜像。

```bash
cd aasp-metrics-adapter

# Dockerfile 要点：chmod + 绝对路径，避免 nobody Permission denied
# FROM python:3.11-slim
# WORKDIR /app
# COPY adapter.py .
# RUN chmod 644 /app/adapter.py && chmod 755 /app
# USER nobody
# CMD ["python", "-u", "/app/adapter.py"]

IMG=swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.2.0
docker build -t "$IMG" .
docker push "$IMG"
```

若仍遇 `Permission denied`，部署时临时加：

```yaml
securityContext:
  runAsUser: 0
```

---

## 3. 部署独立 Adapter Deployment（对照用）

```bash
kubectl create ns aasp-scale-demo --dry-run=client -o yaml | kubectl apply -f -

# 按需修改 deploy.yaml 中镜像名后 apply，或直接用下面清单
```

示例（MOCK=1）：

```bash
IMAGE=swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.2.0

cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aasp-metrics-adapter
  namespace: aasp-scale-demo
  labels:
    app: aasp-metrics-adapter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aasp-metrics-adapter
  template:
    metadata:
      labels:
        app: aasp-metrics-adapter
    spec:
      securityContext:
        runAsUser: 0
      containers:
        - name: adapter
          image: ${IMAGE}
          imagePullPolicy: Always
          ports:
            - name: metrics
              containerPort: 8000
          env:
            - name: MOCK
              value: "1"
            - name: MOCK_RPM
              value: "100"
            - name: MOCK_PROMPT_TPM
              value: "32000"
            - name: MOCK_COMPLETION_TPM
              value: "32000"
            - name: PROJECT_ID
              value: "demo-project"
            - name: SERVICE_GROUP_ID
              value: "mock-predict-serving"
            - name: REGION
              value: "cn-east-204-dev"
            - name: POLL_SECONDS
              value: "15"
            - name: METRICS_PORT
              value: "8000"
          readinessProbe:
            httpGet:
              path: /metrics
              port: metrics
            initialDelaySeconds: 2
            periodSeconds: 5
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
      imagePullSecrets:
        - name: default-secret
---
apiVersion: v1
kind: Service
metadata:
  name: aasp-metrics-adapter
  namespace: aasp-scale-demo
spec:
  selector:
    app: aasp-metrics-adapter
  ports:
    - name: metrics
      port: 8000
      targetPort: 8000
EOF

kubectl -n aasp-scale-demo get pods -l app=aasp-metrics-adapter
kubectl -n aasp-scale-demo port-forward svc/aasp-metrics-adapter 8000:8000
# 另开终端
curl -s http://127.0.0.1:8000/metrics | grep -E 'aasp_predicted_rpm|aasp_adapter_up'
```

期望：`aasp_predicted_rpm ... 100`，`aasp_adapter_up 1`。

> 注意：Kthena Binding **不会**自动刮这个独立 Deployment；扩缩必须以 **ModelServing Pod** 为指标源。独立 Deployment 仅作对照。

---

## 4. 部署三指标 Policy + Binding

先清理旧的单指标配置（若存在）：

```bash
kubectl -n aasp-scale-demo delete autoscalingpolicybinding aasp-predictive-binding --ignore-not-found
kubectl -n aasp-scale-demo delete autoscalingpolicy aasp-predictive-scaling --ignore-not-found
```

创建 multi 策略：

```bash
cat <<EOF | kubectl apply -f -
apiVersion: workload.serving.volcano.sh/v1alpha1
kind: AutoscalingPolicy
metadata:
  name: aasp-predictive-scaling-multi
  namespace: aasp-scale-demo
spec:
  metrics:
    - metricName: aasp_predicted_rpm
      targetValue: 100
    - metricName: aasp_predicted_prompt_tpm
      targetValue: 50000
    - metricName: aasp_predicted_completion_tpm
      targetValue: 50000
  tolerancePercent: 10
  behavior:
    scaleUp:
      stablePolicy:
        stabilizationWindow: 30s
        period: 15s
        percent: 100
        instances: 2
        selectPolicy: Or
      panicPolicy:
        panicThresholdPercent: 200
        panicModeHold: 2m
        period: 15s
        percent: 100
    scaleDown:
      stabilizationWindow: 1m
      period: 30s
      percent: 50
      instances: 1
      selectPolicy: Or
---
apiVersion: workload.serving.volcano.sh/v1alpha1
kind: AutoscalingPolicyBinding
metadata:
  name: aasp-predictive-binding-multi
  namespace: aasp-scale-demo
spec:
  policyRef:
    name: aasp-predictive-scaling-multi
  homogeneousTarget:
    minReplicas: 1
    maxReplicas: 6
    target:
      targetRef:
        apiVersion: workload.serving.volcano.sh/v1alpha1
        kind: ModelServing
        name: mock-predict-serving
      metricEndpoint:
        port: 8000
        uri: /metrics
EOF
```

确认：

```bash
kubectl -n aasp-scale-demo get autoscalingpolicy,autoscalingpolicybinding
kubectl -n aasp-scale-demo get autoscalingpolicybinding aasp-predictive-binding-multi \
  -o jsonpath='{.spec.homogeneousTarget.target.metricEndpoint}{"\n"}'
```

---

## 5. 部署 ModelServing（跑 Adapter，供 Kthena 刮取）

```bash
IMAGE=swr.hcs-lab.ga159arm.com/cce-charts-hcs-lab-a163446a18ae451f91e6083ec1164afe/aasp-metrics-adapter:0.2.0

kubectl -n aasp-scale-demo delete modelserving mock-predict-serving --ignore-not-found

cat <<EOF | kubectl apply -f -
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
            securityContext:
              runAsUser: 0
            containers:
              - name: adapter
                image: ${IMAGE}
                imagePullPolicy: Always
                ports:
                  - name: metrics
                    containerPort: 8000
                env:
                  - name: MOCK
                    value: "1"
                  - name: MOCK_RPM
                    value: "100"
                  - name: MOCK_PROMPT_TPM
                    value: "32000"
                  - name: MOCK_COMPLETION_TPM
                    value: "32000"
                  - name: PROJECT_ID
                    value: "demo-project"
                  - name: SERVICE_GROUP_ID
                    value: "mock-predict-serving"
                  - name: REGION
                    value: "cn-east-204-dev"
                resources:
                  requests:
                    cpu: "50m"
                    memory: "64Mi"
                  limits:
                    cpu: "200m"
                    memory: "128Mi"
            imagePullSecrets:
              - name: default-secret
EOF

kubectl -n aasp-scale-demo get pods -w
```

期望出现：`mock-predict-serving-0-infer-0-0` 且 `1/1 Running`。

---

## 6. 验收：指标被 Kthena 采到

```bash
# 若本机 8000 被占用，换 18000
kubectl -n aasp-scale-demo port-forward pod/mock-predict-serving-0-infer-0-0 18000:8000
```

另开终端：

```bash
curl -s http://127.0.0.1:18000/metrics | grep -E 'aasp_predicted_rpm|aasp_adapter_up'

kubectl -n kube-system logs deploy/kthena-controller-manager --tail=40 \
  | grep -E 'MetricTargets|ReadyInstancesMetrics|recommendedInstances'

kubectl -n aasp-scale-demo get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
```

**通过标准（基线 MOCK_RPM=100）：**

```text
aasp_predicted_rpm ... 100.0
aasp_adapter_up ... 1

MetricTargets: aasp_predicted_rpm=100, prompt_tpm=50000, completion_tpm=50000
ReadyInstancesMetrics: 含 rpm/prompt/completion 数值（不是 [{}]）
recommendedInstances=1
spec=1 status=1
```

计算公式（单 scrape 源、全局值）：

```text
desired ≈ max(rpm/100, prompt_tpm/50000, completion_tpm/50000)
再限制在 [minReplicas, maxReplicas]=[1,6]
```

> 多副本时，若每个 Pod 都暴露同一全局值，Autoscaler 会 **求和 ×N**。  
> 例：6 Pod × rpm=600 → ReadyInstancesMetrics.rpm=3600。  
> 生产应只刮 1 个源，或每 Pod 报 `总量/N`。

---

## 7. 扩容测试（MOCK_RPM=600 → 期望约 6）

```bash
kubectl -n aasp-scale-demo patch modelserving mock-predict-serving --type=json -p='[
  {"op":"replace","path":"/spec/template/roles/0/entryTemplate/spec/containers/0/env","value":[
    {"name":"MOCK","value":"1"},
    {"name":"MOCK_RPM","value":"600"},
    {"name":"MOCK_PROMPT_TPM","value":"32000"},
    {"name":"MOCK_COMPLETION_TPM","value":"32000"},
    {"name":"PROJECT_ID","value":"demo-project"},
    {"name":"SERVICE_GROUP_ID","value":"mock-predict-serving"},
    {"name":"REGION","value":"cn-east-204-dev"}
  ]}
]'

# 重建 Pod 使 env 生效（subPath/旧进程不会热更新 MOCK）
kubectl -n aasp-scale-demo delete pod $(kubectl -n aasp-scale-demo get pods -o name | grep mock-predict | tr '\n' ' ')
kubectl -n aasp-scale-demo get pods -w
```

确认指标与推荐值：

```bash
kubectl -n aasp-scale-demo port-forward pod/mock-predict-serving-0-infer-0-0 18000:8000
curl -s http://127.0.0.1:18000/metrics | grep aasp_predicted_rpm
# 期望 600.0

kubectl -n kube-system logs deploy/kthena-controller-manager --tail=30 \
  | grep -E 'ReadyInstancesMetrics|recommendedInstances'

kubectl -n aasp-scale-demo get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
kubectl -n aasp-scale-demo get pods | grep mock-predict
```

**通过标准：**

- 单副本刚起来时：`600/100=6` → `recommendedInstances` 升向 6  
- 最终：`spec=6 status=6`，约 6 个 `mock-predict-serving-*-infer-0-0` Pod  

（扩到 6 后若日志出现 `rpm=3600`，属 ×N 加总，封顶仍为 max=6，不影响本次扩容验收。）

---

## 8. 缩容测试（MOCK_RPM=10 → 期望回到 1）

即使 6 副本加总：`6×10/100=0.6` → 推荐约 1。

```bash
kubectl -n aasp-scale-demo patch modelserving mock-predict-serving --type=json -p='[
  {"op":"replace","path":"/spec/template/roles/0/entryTemplate/spec/containers/0/env","value":[
    {"name":"MOCK","value":"1"},
    {"name":"MOCK_RPM","value":"10"},
    {"name":"MOCK_PROMPT_TPM","value":"1000"},
    {"name":"MOCK_COMPLETION_TPM","value":"1000"},
    {"name":"PROJECT_ID","value":"demo-project"},
    {"name":"SERVICE_GROUP_ID","value":"mock-predict-serving"},
    {"name":"REGION","value":"cn-east-204-dev"}
  ]}
]'

kubectl -n aasp-scale-demo delete pod $(kubectl -n aasp-scale-demo get pods -o name | grep mock-predict | tr '\n' ' ')
kubectl -n aasp-scale-demo get pods -w
```

观察：部分 Pod 进入 `Terminating`，数量逐步减少。缩容有稳定窗口（约 1 分钟量级），需等待。

```bash
curl -s http://127.0.0.1:18000/metrics | grep aasp_predicted_rpm
# 若 forward 断了，重新 port-forward 后再 curl；期望 10.0

kubectl -n kube-system logs deploy/kthena-controller-manager --tail=20 \
  | grep -E 'ReadyInstancesMetrics|recommendedInstances'

kubectl -n aasp-scale-demo get modelserving mock-predict-serving \
  -o jsonpath='spec={.spec.replicas} status={.status.replicas}{"\n"}'
kubectl -n aasp-scale-demo get pods | grep mock-predict
```

**通过标准：**

- `recommendedInstances` 降到 1  
- 最终只剩 1 个 mock-predict Pod，`spec=1 status=1`

---

## 9. 验收清单（MOCK 全流程）

| # | 项 | 期望 |
|---|----|------|
| 1 | Adapter `/metrics` | 有三指标且 `aasp_adapter_up=1` |
| 2 | Kthena MetricTargets | `rpm` / `prompt_tpm` / `completion_tpm` |
| 3 | ReadyInstancesMetrics | 非空 `[{}]`，有数值 |
| 4 | MOCK_RPM=100 | replicas≈1 |
| 5 | MOCK_RPM=600 | replicas→6 |
| 6 | MOCK_RPM=10 | replicas→1 |

全部通过即证明：在当前 Kthena 版本（仅 Pod `metricEndpoint`）下，用 Adapter 暴露预测指标做弹性扩缩 **可行且可复现**。

---

## 10. 切真 API（可选后续）

AASP：

```text
GET {BASE_URL}/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations
  ?region=...&start_time=...&end_time=...
Authorization: Bearer {TOKEN}
```

Adapter 对 `resources.predictions` 做 **max**，暴露同名 gauge。

```bash
kubectl -n aasp-scale-demo create secret generic aasp-api-token \
  --from-literal=token='<TOKEN>' --dry-run=client -o yaml | kubectl apply -f -
```

ModelServing env 改为：

```text
MOCK=0
BASE_URL=https://apigw-beta.huawei.com
PROJECT_ID=<真实>
SERVICE_GROUP_ID=<真实>
REGION=<真实>
TOKEN 来自 secret aasp-api-token
```

然后删 Pod 重建，确认 `aasp_adapter_up=1` 且峰值与 API 窗口 max 一致。

---

## 11. 常见问题

| 现象 | 原因 / 处理 |
|------|-------------|
| `Permission denied: /app/adapter.py` | 镜像 nobody 权限；`runAsUser: 0` 或重建带 chmod 的镜像 |
| `ImagePullBackOff` | 镜像名 / `default-secret` |
| `ReadyInstancesMetrics: [{}]` | 刮错端口（应为 8000）或 Pod 无指标 |
| 仍出现 `aasp_predicted_requests` | 旧 Binding 未删，删掉非 multi 的 Policy/Binding |
| `currentInstancesCount=6` 但无 Pod | ModelServing status 陈旧 + 控制器未调和；重启控制器并重建 MS |
| Lease `renewTime` 很久不变 | 控制器丢 Leader；rollout restart，且勿调度到坏节点 |
| `port-forward ... address already in use` | 换本地端口如 `18000:8000`，或结束旧 forward |
| 改 MOCK 后指标不变 | 必须删 Pod 重建以加载新 env |
| rpm 被放大 N 倍 | 多 Pod 同报全局值被求和；只刮一个源或报 总量/N |

---

## 12. 清理（可选）

```bash
kubectl delete ns aasp-scale-demo
# 若曾 cordon 坏节点且已修复：
# kubectl uncordon 135.0.0.49
```

---

## 附录：关键公式与映射

| Adapter 指标 | Policy metricName | 示例 targetValue |
|--------------|-------------------|------------------|
| `aasp_predicted_rpm` | 同左 | 100（单实例 RPM） |
| `aasp_predicted_prompt_tpm` | 同左 | 50000 |
| `aasp_predicted_completion_tpm` | 同左 | 50000 |

MOCK 联调建议值：

| 场景 | MOCK_RPM | 期望副本（近似） |
|------|----------|------------------|
| 基线 | 100 | 1 |
| 扩容 | 600 | 6（max） |
| 缩容 | 10 | 1（即使曾有 6 Pod 加总） |
