# deploy.yaml 资源说明

本文解释 `deploy.yaml` 中**每一个 Kubernetes / Kthena 资源**的作用、关键字段，以及它们如何串成「AASP → Adapter → 扩缩容」链路。

> 仓库里的 `deploy.yaml` 默认是 **MOCK 演示**（`MOCK=1`，镜像 tag 可能较旧）。真 API 联调时改 ModelServing 的 image/env（见 `REAL-SCENARIO-TEST-GUIDE.md` / `DESIGN.md`），**不要**再加同名 Lease 的独立 Deployment。

资源出现顺序与依赖关系：

```text
Namespace
  ├── ServiceAccount  aasp-metrics-adapter
  ├── Role / RoleBinding  （Lease 权限）
  ├── Secret  aasp-api-token
  ├── ModelServing  mock-predict-serving   ← 跑 Adapter Pod
  ├── AutoscalingPolicy  …                 ← 怎么算副本
  └── AutoscalingPolicyBinding  …          ← 绑谁、刮哪里、min/max
```

---

## 1. Namespace：`aasp-scale-demo`

```yaml
kind: Namespace
metadata:
  name: aasp-scale-demo
```

| 项 | 说明 |
|----|------|
| **作用** | 隔离本实验的全部对象（RBAC、Secret、MS、Policy、Lease、Pod） |
| **为何需要** | Lease / Role 都是命名空间级；与业务其它负载分开，删 ns 可整体清理 |
| **注意** | ns 若处于 `Terminating`，无法再创建 Pod；需等删完或换新 ns |

---

## 2. ServiceAccount：`aasp-metrics-adapter`

```yaml
kind: ServiceAccount
metadata:
  name: aasp-metrics-adapter
```

| 项 | 说明 |
|----|------|
| **作用** | Adapter 容器的身份；调用 API Server 争用 Lease 时用该 SA 的 Token |
| **谁引用** | `ModelServing` → `serviceAccountName: aasp-metrics-adapter` |
| **为何不直接用 default** | 最小权限：只给选主所需的 leases 权限，避免 default SA 过宽 |

---

## 3. Role：`aasp-metrics-leader`

```yaml
kind: Role
rules:
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

| 项 | 说明 |
|----|------|
| **作用** | 允许在本 ns 内读写 **Lease**（选主） |
| **为何只要 leases** | Adapter 不改其它 K8s 资源；扩缩由 kthena-controller 完成 |
| **缺了会怎样** | 无法 create/update Lease → 选主失败或全体无法当 Leader → 指标异常 |

---

## 4. RoleBinding：`aasp-metrics-leader`

```yaml
kind: RoleBinding
roleRef:
  kind: Role
  name: aasp-metrics-leader
subjects:
  - kind: ServiceAccount
    name: aasp-metrics-adapter
```

| 项 | 说明 |
|----|------|
| **作用** | 把上面的 Role **绑到** ServiceAccount |
| **缺了会怎样** | SA 存在但无权限，表现同 Role 缺失 |

---

## 5. Secret：`aasp-api-token`

```yaml
kind: Secret
type: Opaque
stringData:
  token: "replace-me"
```

| 项 | 说明 |
|----|------|
| **作用** | 存放 AASP 的 `X-Auth-Token` / Bearer Token；可选存放 IAM 密码供自动重登 |
| **真 API 时** | `token`：可选手填初始票；`iam-password`：启用 Adapter 内 401 自动重登时使用 |
| **MOCK 时** | 可不使用 |
| **注意** | 不要把 Token/密码提交进 Git；自动重登只更新进程内存，不写回 Secret |

仓库默认 YAML 的 ModelServing MOCK 段**未**挂载该 Secret；真 API 部署需在容器 env 增加：

```yaml
- name: TOKEN
  valueFrom:
    secretKeyRef:
      name: aasp-api-token
      key: token
```

---

## 6. ModelServing：`mock-predict-serving`

```yaml
kind: ModelServing
metadata:
  name: mock-predict-serving
spec:
  replicas: 1          # ServingGroup 数量（Autoscaler 主要改这个）
  recoveryPolicy: None
  template:
    roles:
      - name: infer
        replicas: 1
        workerReplicas: 0
        entryTemplate: ...
```

这是 **被扩缩的工作负载**，也是 **Adapter 的载体**。

### 6.1 层级含义

| 字段 | 含义 |
|------|------|
| `spec.replicas` | **ServingGroup** 个数 ≈「模型实例组」水平副本；Kthena Autoscaler 写入的目标 |
| `roles[].replicas` | 每个 ServingGroup 内该 Role 的副本 |
| `workerReplicas: 0` | 无额外 worker；本 demo 每 Group 基本 1 个 entry Pod |
| `recoveryPolicy: None` | 不启用额外恢复策略（按环境可改） |

### 6.2 容器与选主相关 env

| 配置 | 作用 |
|------|------|
| `serviceAccountName: aasp-metrics-adapter` | 使用带 Lease 权限的身份 |
| `containerPort: 8000` / name `metrics` | 供 Binding `metricEndpoint` 刮取 |
| `MOCK=1` + `MOCK_*` | 离线演示；真 API 改为 `MOCK=0` + `BASE_URL` / `INSTANCE_ID` / `AUTH_HEADER` 等 |
| `LEADER_ELECTION=1` | 开启 Lease 选主 |
| `LEASE_NAME=aasp-metrics-leader` | 与其它 Adapter **勿冲突**的 Lease 名 |
| `POD_NAME` / `POD_NAMESPACE` | Downward API，选主 identity |
| `imagePullSecrets: default-secret` | 拉私有仓库镜像（集群需已有同名 Secret） |

### 6.3 为何是 ModelServing 而不是 Deployment

- Autoscaler 的 `targetRef` 指向 **ModelServing**，改的是其 `spec.replicas`。  
- 与 Kthena/Volcano 的 ServingGroup 调度、扩缩语义一致。  
- Adapter 跟 MS Pod 同生共死，缩容删 Leader 后其它 Pod 可接手 Lease。

---

## 7. AutoscalingPolicy：`aasp-predictive-scaling-multi`

```yaml
kind: AutoscalingPolicy
spec:
  metrics:
    - metricName: aasp_predicted_rpm
      targetValue: 100
    - ...
  tolerancePercent: 10
  behavior:
    scaleUp: ...
    scaleDown: ...
```

| 块 | 作用 |
|----|------|
| **metrics** | 使用哪些 Adapter 指标、每个指标的目标值；理想副本 ≈ `ceil(指标/targetValue)`，多指标再综合 |
| **tolerancePercent** | 当前副本与理想差太小则不动作，防抖 |
| **behavior.scaleUp** | 扩容速度：稳定策略 + panic 突发策略 |
| **behavior.scaleDown** | 缩容速度：通常更慢（稳定窗更长、每步 instances 更小） |

**不含**「扩谁、刮哪里、min/max」——那些在 Binding。  
修改 Policy 一般热生效，以控制器日志 `MetricTargets` 校验。

---

## 8. AutoscalingPolicyBinding：`aasp-predictive-binding-multi`

```yaml
kind: AutoscalingPolicyBinding
spec:
  policyRef:
    name: aasp-predictive-scaling-multi
  homogeneousTarget:
    minReplicas: 1
    maxReplicas: 6
    target:
      targetRef:
        kind: ModelServing
        name: mock-predict-serving
      metricEndpoint:
        port: 8000
        uri: /metrics
```

| 字段 | 作用 |
|------|------|
| `policyRef` | 使用哪份 Policy（算法与 behavior） |
| `targetRef` | 扩缩哪个 ModelServing |
| `minReplicas` / `maxReplicas` | 副本上下限（夹紧 recommended） |
| `metricEndpoint` | 从 MS 的 Pod 上刮 `port`+`uri`；1.22.1 **刮该目标下相关 Pod** |

与选主的关系：刮取所有 Pod 时，Follower 指标为 0，求和等于 Leader 峰值，避免 ×N。

---

## 9. 未写在 YAML、但运行时会出现的对象

| 对象 | 谁创建 | 作用 |
|------|--------|------|
| `Lease/aasp-metrics-leader` | Adapter Leader | 选主；`holderIdentity` 为当前 Leader Pod 名 |
| Pod / PodGroup | kthena + volcano | 实际负载；名称形如 `mock-predict-serving-<g>-infer-0-0` |
| 控制器 Lease（`kube-system`） | kthena-controller | 与 Adapter Lease **无关**；控制器自身选主 |

`deploy.yaml` **故意不包含**独立的 Adapter `Deployment`/`Service`，避免抢 Lease。

---

## 10. 一张表：谁依赖谁

| 资源 | 依赖 | 被谁用 |
|------|------|--------|
| Namespace | — | 其它全部 |
| ServiceAccount | Namespace | ModelServing、RoleBinding |
| Role | Namespace | RoleBinding |
| RoleBinding | SA + Role | （授权生效） |
| Secret | Namespace | ModelServing（真 API 时） |
| ModelServing | SA、镜像、可选 Secret | Binding 的 target；产生 Pod/Lease |
| AutoscalingPolicy | Namespace | Binding 的 policyRef |
| AutoscalingPolicyBinding | Policy + ModelServing | kthena Autoscaler |

---

## 11. apply 后建议检查

```bash
kubectl -n aasp-scale-demo get ns,sa,role,rolebinding,secret,modelserving,autoscalingpolicy,autoscalingpolicybinding,pods,lease
```

期望：MS Pod Running；存在 `lease/aasp-metrics-leader`；无多余 adapter Deployment。
