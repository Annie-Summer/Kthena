# 基于 AASP 预测的 Kthena 弹性扩缩容设计

> 适用范围：华为云 CCE / HCS 上的 **Kthena `kthena-controller-manager:1.22.1`**（`AutoscalingPolicy` + `AutoscalingPolicyBinding` + `ModelServing`，Binding 仅支持 `metricEndpoint` Pod 刮取）。  
> 实现目录：`aasp-metrics-adapter/`  
> 验证结论：真实 AASP API → Adapter（Lease 选主）→ Binding 刮取 → 改写 `ModelServing.spec.replicas` 已在实验室打通。

---

## 1. 目标与问题

### 1.1 目标

根据 **AASP（智能预测）** 给出的未来/窗口内负载预测（rpm、prompt/completion token 等），自动调整推理服务的 **ModelServing ServingGroup 副本数**，实现**预测驱动**的弹性扩缩容，而不是只对瞬时实时指标做被动反应。

### 1.2 平台约束（为何需要 Adapter）

| 约束 | 影响 |
|------|------|
| Kthena 1.22.1 Binding 只有 `metricEndpoint` | 只能刮 **Pod 上的 Prometheus 文本指标**，不能直接配 Prometheus 远程查询 |
| 不引入 AOM、不升级社区 Kthena 1.0.0 | 不能依赖 `metricSources.prometheus`；必须自建“预测 → Pod `/metrics`”桥接 |
| AASP 是 HTTP JSON API | 需要进程周期拉取、归一化字段、暴露 gauge |
| ModelServing 会扩出多个 Pod | 若每个 Pod 都暴露同一全局预测，控制器按 Pod **求和**会 ×N |

因此引入 **AASP Metrics Adapter**：跑在 ModelServing Pod 内（当前可为 sole container；生产可作 sidecar），完成「拉 AASP → 暴露指标 → 供 Binding 刮取」。

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                         AASP 服务                                │
│  GET /v1/{project}/instance/{id}/infer-recommendations           │
│  Header: X-Auth-Token                                            │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 仅 Leader 轮询（POLL_SECONDS）
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  ModelServing（N 个 ServingGroup ≈ N 个 Adapter Pod）              │
│                                                                   │
│   Pod-0 (Leader)          Pod-1 (Follower)     Pod-k (Follower)   │
│   ┌──────────────┐        ┌──────────────┐     ┌──────────────┐  │
│   │ 拉 AASP      │        │ 不拉 AASP    │     │ 不拉 AASP    │  │
│   │ /metrics:    │        │ /metrics:    │     │ /metrics:    │  │
│   │  rpm=峰值    │        │  rpm=0       │     │  rpm=0       │  │
│   │  up=1/0      │        │  up=0        │     │  up=0        │  │
│   └──────────────┘        └──────────────┘     └──────────────┘  │
│           ▲ 争用 Lease: aasp-metrics-leader                        │
└───────────┼─────────────────────────────────────────────────────┘
            │ metricEndpoint 刮取所有 Ready Pod :8000/metrics
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  AutoscalingPolicyBinding + AutoscalingPolicy                     │
│  汇总（求和后 = 全局峰值）→ recommended → behavior 限速            │
│  → 写 ModelServing.spec.replicas（ServingGroup 数）               │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  kthena-controller-manager（自身也有 kube-system Lease 选主）     │
│  创建/删除 ServingGroup 与 Pod                                      │
└─────────────────────────────────────────────────────────────────┘
```

数据面一句话：**预测是全局的一份；指标面通过选主变成“只有一份非零值”，从而兼容“刮全部 Pod 再求和”的 Autoscaler。**

---

## 3. 从 AASP 真 API 获取数据

### 3.1 调用方式

实验室已验证路径（instance 风格）：

```http
GET {BASE_URL}/v1/{PROJECT_ID}/instance/{INSTANCE_ID}/infer-recommendations
    ?start_time={ISO8601}&end_time={ISO8601}&region={REGION}
Header: X-Auth-Token: {TOKEN}
```

示例：

```text
BASE_URL=http://52.170.215.202:8088
PROJECT_ID=5dfed145e29a43f7b42c5ecc17d4d98c
INSTANCE_ID=922ae983-addb-46e8-8096-5092de62af13
REGION=cn-north-5
AUTH_HEADER=x-auth-token
```

兼容路径（网关/旧文档）：

```text
GET {BASE_URL}/v1/{PROJECT_ID}/{SERVICE_GROUP_ID}/infer-recommendations?...
Authorization: Bearer {TOKEN}
```

Adapter 规则：设置了 `INSTANCE_ID` 则走 instance 路径；否则走 `SERVICE_GROUP_ID` 路径。鉴权由 `AUTH_HEADER=x-auth-token|bearer` 选择。

### 3.2 时间窗（决定“采的是哪一段预测”）

| 环境变量 | 含义 |
|----------|------|
| `WINDOW_MINUTES` | 窗口长度（如 `10` = 10 分钟） |
| `TIME_RANGE_MODE=backward` | `[now−W, now]`，回顾窗 |
| `TIME_RANGE_MODE=forward`（默认若未设 backward） | `[now, now+W]`，**面向未来的预测窗**（预测扩缩建议用这个） |
| `POLL_SECONDS` | 多久拉一次（如 15s）；不改变窗口长度，只改变滑动频率 |

时间格式：`YYYY-MM-DDTHH:MM:SS`（与 AASP 校验一致；错误格式会 400）。

**预测扩缩语义：** 使用 `forward`，让扩缩决策基于“未来 W 分钟”的预测峰值，而不是仅对过去窗做回放。

### 3.3 响应解析与峰值策略

实验室真实响应形态（多 service group 映射）：

```json
{
  "resources": {
    "<group_a>": {
      "region": "cn-north-5",
      "prediction": [
        { "rpm": 2976.7, "prompt_token": 100709.3, "completion_token": 49938.1 }
      ]
    },
    "<group_b>": {
      "prediction": [
        { "rpm": 2992.7, "prompt_token": 102282.0, "completion_token": 51007.0 }
      ]
    }
  }
}
```

Adapter 归一化要点：

1. 支持 `resources` 为：**扁平对象**、**数组**、或 **group_id → 对象** 的 map。  
2. 支持字段别名：`prediction` / `predictions`；`prompt_token` / `prompt_tpm`；`completion_token` / `completion_tpm`。  
3. **峰值策略：** 对窗口内所有点、所有 group 取 **max**（不是 avg，不是只取最后一个点）。  
4. 失败策略：保留上一拍成功值，`aasp_adapter_up=0`，并打 warning 日志（避免扩缩因瞬时 API 失败抖动到底）。

暴露的 Prometheus 指标：

| 指标 | 含义 |
|------|------|
| `aasp_predicted_rpm` | 窗口内 rpm 峰值 |
| `aasp_predicted_prompt_tpm` | prompt 侧峰值（token 字段映射到该名） |
| `aasp_predicted_completion_tpm` | completion 侧峰值 |
| `aasp_adapter_up` | Leader 且最近一次拉取成功 |
| `aasp_adapter_is_leader` | 是否持有 Lease |

### 3.4 网络与凭证

- 集群 Pod 必须能直达 `BASE_URL`（VPC 互通 / 正确入口 IP；代理不通时不要强行走坏代理）。  
- Token 放在 Secret（如 `aasp-api-token`），以 env `TOKEN` 注入；`AUTH_HEADER` 只表示头模式，不是 Token 本身。  
- 镜像需含 instance 路径 + 实验室响应解析（建议 **0.4.1+**）。

### 3.5 为何由 Adapter 拉，而不是控制器直连 AASP

- 保持 Kthena 1.22.1 不变：仍只懂 Prometheus scrape。  
- 预测 API 的鉴权、时间窗、字段差异集中在一处，便于 MOCK/真 API 切换。  
- 与推理进程同生命周期部署（sidecar 或同 Pod），扩缩时指标端点自然随 ServingGroup 存在。

---

## 4. Adapter 选主设计

### 4.1 要解决的本质问题

Kthena Binding 配置为刮取 **目标 ModelServing 下全部 Pod** 的 `/metrics`，再对同名指标做聚合（实践中为 **求和**）。

AASP 预测是 **全局一份**（按 project/instance），不是“每个推理副本一份”。若 N 个 Pod 都暴露 `rpm=3000`，控制器会看到约 `3000×N`，副本被严重高估。

### 4.2 方案选择

| 方案 | 做法 | 问题 |
|------|------|------|
| A. 独立 Deployment 单副本 Adapter + 只刮该 Service | 指标天然一份 | 与 MS 生命周期分离；Binding 仍指向 MS 时对不上；且勿与 MS 共用同一 `LEASE_NAME`（会抢主导致 MS 指标全 0） |
| B. 只刮某一个 MS Pod | 需稳定选中单 Pod | 1.22.1 Binding 不便表达；缩容删掉被刮 Pod 会断指标 |
| **C. 每个 MS Pod 跑 Adapter + Lease 选主（采用）** | Leader 出真实值，Follower 出 0 | 刮全部 Pod 时求和 = 全局峰值；Leader 被缩掉可在 TTL 内重选 |

### 4.3 选主机制

- 资源：`coordination.k8s.io/v1` **Lease**（默认名 `aasp-metrics-leader`）。  
- 身份：`POD_NAME`（Downward API）。  
- 周期：默认 `LEASE_DURATION_SECONDS=15`，`LEASE_RENEW_SECONDS=5`。  
- RBAC：ServiceAccount + Role/RoleBinding，仅需对本 ns 的 leases `get/create/update`。  
- 行为：
  - **Leader：** 轮询 AASP；`/metrics` 暴露峰值与 `aasp_adapter_is_leader=1`。  
  - **Follower：** 不访问 AASP；预测类 gauge 为 `0`，`is_leader=0`。

### 4.4 为什么这样设计

1. **兼容现有刮取模型**：无需改 Kthena 聚合逻辑，也不要求 Binding 支持 “只刮一个 endpoint”。  
2. **高可用**：Leader 随 ServingGroup 缩容消失后，其它 Pod 争用 Lease，指标短中断后恢复（秒～十几秒级，与 Lease TTL 相关）。  
3. **降压 AASP**：任意时刻只有 1 个轮询者，避免 N 倍打爆预测服务。  
4. **运维简单**：不额外养一套独立指标 Deployment；与推理拓扑同 ns 同 RBAC 边界。

### 4.5 部署注意

- Adapter **必须**跑在被 Binding 刮取的 ModelServing Pod 上（可 sole / sidecar）。  
- **不要**再部署同 `LEASE_NAME` 的独立 Adapter Deployment，否则会抢走 Leadership，MS Pod 全是 Follower → 指标全 0 → 扩缩失灵或缩到 min。  
- 验证：`kubectl get lease aasp-metrics-leader` 的 holder 应为某个 `mock-predict-serving-*-infer-*-*`；控制器日志 `ReadyInstancesMetrics` 应 **只有一组**接近 Leader 峰值的数，而不是 N 倍。

---

## 5. Kthena 弹性扩缩容

### 5.1 相关对象（1.22.1）

| 对象 | 职责 |
|------|------|
| `ModelServing` | 推理工作负载蓝图；`spec.replicas` = **ServingGroup 数量**（Autoscaler 主要改这个） |
| `AutoscalingPolicy` | 指标名、`targetValue`、`tolerancePercent`、`behavior`（升/降速与 panic） |
| `AutoscalingPolicyBinding` | 绑定 Policy ↔ ModelServing；`minReplicas`/`maxReplicas`；`metricEndpoint` |

社区更新版本可能把 Binding 合进 Policy 并增加 Prometheus source；本设计固定在 1.22.1 的拆分模型上。

### 5.2 决策链路

```text
1. 刮取所有 Ready Pod 的 aasp_predicted_* （Follower 为 0）
2. 得到 ReadyInstancesMetrics（实践中总和 = Leader 峰值）
3. 对每个指标：理想副本 ≈ ceil(当前指标值 / targetValue)
4. 多指标取更“要容量”的结果（max），再夹紧到 [minReplicas, maxReplicas]
5. tolerancePercent：|当前副本 - 理想| 不足阈值则跳过
6. behavior 限速：stabilizationWindow / period / instances / percent / panic
7. 得到 correctedInstances → 写 ModelServing.spec.replicas
8. ModelServing 控制器增删 ServingGroup（从而增删 Pod）
```

示例：`rpm=3062`，`targetValue=500` → `3062/500=6.125` → **ceil=7**（不是截断成 6）。

### 5.3 `behavior` 在扩缩中的作用（摘要）

- **scaleUp.stablePolicy**：常规扩容防抖与步长（如每 15s 最多 +2 或 +100%）。  
- **scaleUp.panicPolicy**：理想副本相对当前过高（如 ≥ 200%）时加速扩。  
- **scaleDown**：通常更保守（如 `stabilizationWindow: 1m`，每步少 `instances:1`），故常见 **`spec` 先变、`status`/Pod 后降**。  

`spec.replicas` = 期望 ServingGroup 数；`status.replicas` = 仍存在的 ServingGroup 数（含删除中）。二者短期不一致是预期现象。

### 5.4 与“实时指标扩缩”的差异

| | 实时指标 HPA 类 | 本方案（AASP 预测） |
|--|----------------|-------------------|
| 输入 | 当前 QPS/CPU/队列 | AASP 窗口内**预测峰值** |
| 目标 | 追上已经发生的负载 | **提前**按预测备容量 |
| 指标来源 | 推理进程自身 metrics | Adapter 从 AASP 注入的 gauge |
| 风险 | 扩容滞后于突发 | 依赖预测质量与时间窗（forward/backward） |

### 5.5 运维要点

- 改 Policy / Binding 一般为 **热更新**，无需重启业务 Pod；以 `kubectl get` 与控制器 Leader 日志中 `MetricTargets` 为准验证。  
- 控制器自身依赖 `kube-system` 中 `lease.kthena.controller-manager`；`renewTime` 过期会导致不调和（表现为有 MS 无 Pod、指标不更新）。异常时 `rollout restart deploy/kthena-controller-manager`。  
- 演示缩容时需让 `ceil(metric/target)` 明显低于当前副本，并考虑 `scaleDown` 窗口；仅微调 target 但理想值仍等于当前时，副本不会动。

---

## 6. 端到端验收标准

1. Pod 内（或节点）能访问 AASP，HTTP 200 且含 `prediction`/`predictions` 数据。  
2. Leader 日志周期性出现 `updated peaks rpm=... points=...`；`aasp_adapter_up 1`。  
3. `ReadyInstancesMetrics` 中 rpm 与 Leader 同量级，**不是** `N ×` Leader。  
4. 调整 `targetValue` / 预测值后，`recommendedInstances` 变化，`ModelServing.spec.replicas` 随之变化（受 min/max 与 behavior 约束）。  
5. 缩容删除 Leader Pod 后，Lease holder 迁移，指标在 TTL 内恢复。

---

## 7. 关键配置一览

```yaml
# Adapter（ModelServing 容器 env）
MOCK: "0"
BASE_URL: "http://<aasp-host>:8088"
PROJECT_ID: "<project>"
INSTANCE_ID: "<instance>"
REGION: "cn-north-5"
AUTH_HEADER: "x-auth-token"
TOKEN: from secret
TIME_RANGE_MODE: "forward"          # 预测未来窗；联调也可用 backward
WINDOW_MINUTES: "10"
POLL_SECONDS: "15"
LEADER_ELECTION: "1"
LEASE_NAME: "aasp-metrics-leader"

# Binding
homogeneousTarget.minReplicas / maxReplicas
metricEndpoint.port: 8000
metricEndpoint.uri: /metrics

# Policy
metrics: aasp_predicted_rpm / prompt_tpm / completion_tpm + targetValue
tolerancePercent
behavior.scaleUp / scaleDown
```

---

## 8. 参考

- 实现：`adapter.py`、`leader_election.py`、`deploy.yaml`  
- 操作手册：`REAL-SCENARIO-TEST-GUIDE.md`、`TEST-GUIDE.md`  
- PR / 代码分支：仓库 `aasp-metrics-adapter/`（选主 + 真 API 解析 ≥ 0.4.1）
