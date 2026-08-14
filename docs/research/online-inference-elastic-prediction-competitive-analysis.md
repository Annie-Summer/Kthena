# 在线推理弹性预测：友商调研与方案对比

> 调研范围：公有云托管推理平台 + 云原生弹性层（可与推理产品联动）  
> 资料来源：各厂商公开文档 / 产品页 / 技术博客（截至 2026-08）  
> 适用对象：云计算厂商规划「在线推理弹性预测」能力时的竞品对标与方案选型

---

## 1. 问题定义与能力分层

### 1.1 什么是「在线推理弹性预测」

在线推理（尤其 GPU / LLM）扩容存在显著冷启动：拉起实例、拉镜像、加载权重、预热 KV Cache，常需数十秒到数分钟。纯反应式 HPA（指标超阈值后再扩）往往**扩容完成时流量峰值已过或已造成超时**。

**弹性预测**指：基于历史流量 / 资源画像做时序预测，在峰谷到来前主动调整副本与资源，并与被动兜底策略组合，在 SLA 与成本之间取得平衡。

### 1.2 能力分层（对标统一口径）

| 层级 | 机制 | 是否“预测” | 典型能力 |
| --- | --- | --- | --- |
| L1 反应式弹性 | Target Tracking / HPA / KEDA | 否 | 按 QPS、并发、CPU/GPU、队列、Token 利用率扩缩 |
| L2 计划式弹性 | Cron / Scheduled Scaling | 弱（人工先验） | 按业务时段预设 min/max 或目标副本 |
| L3 预测式弹性 | Predictive / IHPA / AHPA | 是 | 时序预测 + 冷启动前置量（scale-up forward） |
| L4 推理语义弹性 | LLM/引擎态感知 | 增强 | 按 KV Cache、waiting requests、PD 角色独立伸缩、容量感知实例池 |

业界现状：**多数托管推理产品停留在 L1+L2**；真正产品化 L3 多在 **容器平台（ACK AHPA、火山 VKE IHPA、AWS ECS Predictive Scaling）**，再与推理工作负载联动；L4 是大模型时代的差异化方向。

---

## 2. 友商方案调研摘要

### 2.1 国际三大云（托管推理）

#### AWS SageMaker AI

- **弹性形态**：Application Auto Scaling 的 Target Tracking、Step Scaling、Scheduled Scaling。
- **预测能力**：Application Auto Scaling 的 **Predictive Scaling 目前仅支持 ECS**，SageMaker Endpoint / Inference Component **不支持**原生预测扩缩。
- **推理侧亮点**：
  - 亚分钟级 CloudWatch 指标（10s/30s），扩容感知可快约 6×；
  - Inference Component + 数据/镜像缓存，缩短扩容路径；
  - Capacity-aware Instance Pools：扩容时按优先级回退实例类型。
- **Scale-to-Zero**：Serverless Endpoint 可按调用计费；Real-time Endpoint 常规最小实例 ≥1。
- **适用判断**：运维成熟、冷启动优化强，但 **L3 预测未打通到推理产品**。

#### Azure Machine Learning Online Endpoints

- **弹性形态**：Azure Monitor Autoscale（指标 + 计划）。
- **预测能力**：Online Endpoint **无原生预测扩缩**；计划伸缩可覆盖潮汐业务。
- **Scale-to-Zero**：Online Endpoint **不支持缩到 0**（至少 1 副本）；Batch Endpoint 可缩 0。
- **适用判断**：企业托管体验完整，但弹性深度与 LLM 语义指标相对保守。

#### Google Cloud Vertex AI Inference

- **弹性形态**：Dedicated Endpoint 反应式自动扩缩；默认目标利用率约 60%。
- **指标丰富度（偏 L4）**：CPU、GPU duty cycle、DCGM util、request count，以及 **vLLM KV Cache / waiting requests** 等。
- **Scale-to-Zero**：Dedicated Endpoint **Preview 支持 min=0**（冷启动可达数分钟；扩容期间可能 429，需客户端重试）。
- **预测能力**：托管侧未见与 ECS Predictive 同级的流量预测产品化能力。
- **适用判断**：**LLM 指标与 Scale-to-Zero 领先**，预测层仍弱。

### 2.2 国内主流云（托管推理 + 云原生联动）

#### 阿里云 PAI-EAS + ACK AHPA

- **EAS（推理产品层）**：
  - 水平自动扩缩：QPS / CPU / GPU / 异步队列 / 自定义指标；
  - 定时扩缩容；可与水平策略叠加（改 min/max）；
  - **支持缩到 0**（专属网关等场景有限制）；
  - 弹性资源池：专属资源不足时溢出到公共按量池。
- **ACK AHPA（预测层，可服务推理负载）**：
  - 基于历史指标学习，**主动预测 + 被动兜底**；
  - `prediction.quantile`、`scaleUpForward`（按冷启动时长提前扩容）；
  - 模式：observer / auto / proactive / reactive；
  - 建议 ≥7 天历史数据；支持 CPU/GPU/Memory/QPS/RT。
- **适用判断**：**「EAS 托管弹性 + ACK 预测弹性」双层最完整**，国内对标标杆之一。

#### 腾讯云 TI-ONE

- **弹性形态**：定时、HPA、**定时+HPA 组合**（分时段切换 HPA 边界与阈值）。
- **LLM 指标**：CPU/GPU、单副本 QPS、处理中请求数、输入输出 Token、**Token 利用率**。
- **架构弹性**：PD 分离多角色部署，**按角色独立扩缩容**。
- **预测能力**：公开文档以计划 + 反应式为主，**未见独立时序预测控制器产品化**。
- **适用判断**：LLM 生产运维（PD、Token 指标、组合策略）强，L3 预测相对弱。

#### 华为云 ModelArts（新版推理）

- **弹性形态**：手动扩缩；自动扩缩含 **CRON_HPA / METRIC_HPA**。
- **约束**：自动扩缩多要求部署在**专属资源池**。
- **预测能力**：公开能力以计划 + 指标为主，未见 AHPA/IHPA 级预测产品。
- **适用判断**：满足基础弹性，差异化不足。

#### 火山引擎（MLP 在线服务 + VKE IHPA + AI 推理套件）

- **MLP 在线服务**：定时 / 指标扩缩（GPU util 等），多部署与预付+后付混合。
- **VKE IHPA（智能伸缩）**：
  - 明确对标 HPA/CronHPA 滞后问题；
  - 结合内部时序预测，构建资源画像，**提前扩容**；
  - 面向突发与周期性流量。
- **AI 云原生推理套件**：KEDA 自定义指标、PD 分离独立伸缩、复合指标。
- **适用判断**：**容器层预测叙事清晰（IHPA）**，与字节大规模推理实践绑定；托管 MLP 本身仍以 L1+L2 为主。

#### 百度智能云 千帆

- **弹性形态**：专属推理服务以**控制台/API 手动或脚本扩缩**为主。
- **预测 / 自动 HPA**：公开文档中自动化与预测能力相对薄弱。
- **适用判断**：更偏模型服务与 Agent 平台，弹性预测非主战场。

### 2.3 开源 / 中立参考（自建或底座）

| 方案 | 弹性特点 | 与「预测」关系 |
| --- | --- | --- |
| KServe + Knative KPA | 并发/RPS、Scale-to-Zero、Panic 窗口 | 反应式为主；冷启动仍是痛点 |
| KServe Standard + HPA/KEDA | CPU/自定义指标 | 可外挂预测控制器 |
| Ray Serve Autoscaler | 队列/副本自动 | 偏反应式；可接外部预测 API |
| 学术/系统方案（SageServe、FlashServe 等） | ARIMA / Prophet-LSTM 等预测预热 | 证明 L3+冷启动优化对 LLM 必要，产品化仍分散 |

---

## 3. 方案对比表

### 3.1 总览对比（托管推理视角）

| 维度 | AWS SageMaker | Azure ML Online | GCP Vertex AI | 阿里云 PAI-EAS | 腾讯云 TI-ONE | 华为 ModelArts | 火山 MLP/方舟生态 | 百度千帆 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 反应式 HPA（L1） | ✅ 强 | ✅ | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ✅ | ⚠️ 弱（偏手动） |
| 定时/计划（L2） | ✅ | ✅ | ⚠️ 弱/间接 | ✅ | ✅（含组合策略） | ✅ | ✅ | ❌/弱 |
| **预测弹性（L3）** | ❌ 推理侧无；ECS 有 | ❌ | ❌ | ⚠️ **ACK AHPA 可联动** | ❌/弱 | ❌/弱 | ⚠️ **VKE IHPA 可联动** | ❌ |
| LLM 语义指标（L4） | 并发/调用类 | 偏资源指标 | ✅ vLLM/KV/waiting | QPS/GPU/队列 | ✅ Token/进行中请求 | 偏资源/通用 | GPU + 套件自定义 | 弱 |
| Scale-to-Zero | Serverless ✅ / Realtime 通常否 | ❌ Online | ✅ Preview | ✅（有约束） | 视配置 | 视配置 | MLP 自动扩缩通常 ≥1 | 弱 |
| 冷启动优化 | 镜像/组件缓存、亚分钟指标 | 一般 | Scale-from-zero 仍慢 | 弹性资源池 + 缓存类能力 | PD/镜像优化 | 一般 | 推理套件/P2P 加载等 | 一般 |
| PD 分离独立伸缩 | 非一等公民 | 弱 | 生态/自建 | 支持方向中 | ✅ 角色级 | 弱 | ✅ 套件侧 | 弱 |
| 容量/库存兜底 | ✅ Instance Pools | 区域容量依赖 | Reservation 建议 | ✅ 弹性资源池 | 资源组/潮汐 | 专属池 | 预留/混合计费 | 算力单元约束 |
| 综合定位 | 冷启动与企业治理强 | 企业托管稳妥 | LLM 指标与缩 0 领先 | **托管+预测双层最完整** | LLM 生产策略强 | 基础完备 | **预测叙事+大规模实践** | 平台能力偏上、弹性偏弱 |

图例：✅ 明确具备｜⚠️ 部分具备/需跨产品联动｜❌ 公开能力缺失或很弱

### 3.2 「弹性预测」专项对比（L3）

| 方案 | 所属层 | 预测输入 | 决策输出 | 冷启动处理 | 与反应式关系 | 推理产品内建度 |
| --- | --- | --- | --- | --- | --- | --- |
| 阿里云 ACK AHPA | 容器平台 | ≥7 天 Prometheus 历史（CPU/GPU/Mem/QPS/RT） | 预测副本；分位数可配 | `scaleUpForward` 按 Ready 时长提前扩 | observer/auto/proactive/reactive 可组合 | ⚠️ 需与 EAS/自建推理联动 |
| 火山 VKE IHPA | 容器平台 | 历史用量 + 时序预测资源画像 | 提前调整副本 | 以预测前置扩容解决滞后 | 对标并补齐 HPA/Cron 短板 | ⚠️ 需与 MLP/推理套件联动 |
| AWS Predictive Scaling | 应用弹性（ECS） | 最多 14 天指标，预测未来 48h，约 6h 更新 | 预测容量 | 按预测提前备容 | 可与动态策略并存 | ❌ 未贯通 SageMaker |
| 定时扩缩（各云通用） | L2 | 人工业务先验 | 固定时段目标/边界 | 可“伪预测”提前扩 | 常与 HPA 改 min/max 组合 | ✅ 多数推理产品内建 |
| 纯 HPA（各云通用） | L1 | 实时指标 | 滞后扩缩 | 不主动处理冷启动 | — | ✅ 标配 |

### 3.3 扩缩指标对比（在线推理常用）

| 指标类型 | AWS | Azure | GCP Vertex | 阿里 EAS | 腾讯 TI | 华为 | 火山 MLP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CPU / Memory | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GPU Util / Duty | ✅（增强指标） | 有限 | ✅ | ✅ | ✅ | ✅ | ✅ |
| QPS / Invocations | ✅ | 可配 | ✅ request count | ✅ | ✅ | 视版本 | 视策略 |
| 并发 / 进行中请求 | ✅ ConcurrentRequests* | 有限 | waiting requests | 自定义 | ✅ | 有限 | 自定义/套件 |
| 异步队列长度 | Async 场景 | 弱 | 弱 | ✅ | 弱 | 弱 | 弱 |
| Token / KV Cache | 弱/自建 | 弱 | ✅ vLLM 指标 | 路由/引擎侧增强 | ✅ Token 利用率 | 弱 | 套件侧可做 |
| 自定义指标 | CloudWatch 自定义 | Azure Monitor | 有限扩展 | ✅ | 部分 | 部分 | KEDA/自定义 |

---

## 4. 关键洞察

1. **预测能力「产品化断层」**：真正叫得响的 L3（AHPA / IHPA / Predictive Scaling）多在 **K8s/容器弹性面**；托管推理控制台仍以 HPA+Cron 为主。谁先把「预测控制器」一等公民化进推理产品，谁就有差异化。
2. **LLM 让反应式更不够用**：GPU 冷启动 + KV 状态 + PD 不对称伸缩，使「指标超阈再扩」的失败成本更高；行业在补 **语义指标（L4）** 与 **预测预热（L3）**。
3. **Cron 仍是性价比最高的“弱预测”**：潮汐明显业务上，定时改 min/max 往往比不成熟的预测模型更稳；头部厂商都在推 **Cron ⊕ HPA**。
4. **Scale-to-Zero ≠ 弹性预测**：缩 0 优化闲时成本，但放大冷启动；没有预测预热/请求缓冲时，不适合强实时在线 SLA。
5. **库存与扩容成功率成为隐藏瓶颈**：阿里弹性资源池、AWS Instance Pools、GCP Reservation 说明——预测对了还要 **能买到卡**。
6. **国内对比结论**：
   - **预测技术叙事**：火山 IHPA、阿里 AHPA 领先；
   - **推理产品完整度**：阿里 EAS、腾讯 TI（LLM 指标/PD）领先；
   - **国际侧**：GCP 指标与缩 0、AWS 冷启动工程与容量感知更强，但 L3 未进推理主路径。

---

## 5. 对我方方案的建议（可落地产品路径）

### 5.1 推荐目标架构（三层闭环）

```text
流量/引擎指标 ──► 特征与画像 ──► 时序预测器 ──► 弹性决策引擎 ──► 推理调度/扩缩
     ▲                │              │              │
     │                └──── 分位数/风险偏好 ──────────┤
     │                                               ▼
     └────────────── 反应式兜底（HPA/KEDA） ◄── 扩缩执行与库存感知
                     计划策略（Cron 边界）
```

### 5.2 能力优先级（建议）

| 优先级 | 能力 | 原因 |
| --- | --- | --- |
| P0 | LLM 语义指标 HPA（waiting / KV / Token / 队列）+ Cron⊕HPA | 立即缩小与 TI/Vertex 差距 |
| P0 | 冷启动预算进入决策（scale-up forward） | 没有它，预测无法变成 SLA |
| P1 | 托管内建「智能预测扩缩」（对标 AHPA/IHPA） | 核心差异化，避免只做反应式 |
| P1 | 容量感知扩容（多规格回退/弹性资源池） | 预测有效的前提是扩得出来 |
| P2 | Scale-to-Zero + 请求缓冲/重试协议 | 降本场景；需与预测预热绑定 |
| P2 | PD 角色独立预测与伸缩 | 大模型成本与尾延迟关键杠杆 |

### 5.3 与友商对标策略（简表）

| 若竞争焦点是… | 主要对标 | 我方应强调 |
| --- | --- | --- |
| 预测准确与提前量 | 阿里 AHPA、火山 IHPA | 推理场景特征（Token/KV/活动会话）而非泛 CPU 预测 |
| LLM 生产弹性 | 腾讯 TI、GCP Vertex | Token/KV/PD 一等公民指标与策略模板 |
| 企业稳定性与扩容成功率 | AWS SageMaker、阿里弹性资源池 | 亚分钟检测 + 缓存 + 多规格库存兜底 |
| 闲时成本 | GCP/阿里 Scale-to-Zero | 「预测预热 + 缩 0」组合，避免裸缩 0 |

---

## 6. 结论

当前友商在线推理弹性呈现 **「L1+L2 标配、L3 在容器层萌芽、L4 随 LLM 加速」** 的格局。尚无厂商在「托管推理控制台」内把 **流量预测 → 冷启动前置 → 语义指标兜底 → 库存回退** 做成完整闭环。

对云计算厂商而言，短期应用 **Cron⊕语义 HPA⊕冷启动感知** 快速追平；中期应把 **弹性预测控制器产品化进在线推理**，并与 PD 分离、资源池联动——这是最清晰的差异化窗口。

---

## 附录：主要公开资料

- AWS SageMaker Auto Scaling / Application Auto Scaling（含 Predictive Scaling 仅 ECS）
- Azure ML：Online Endpoint Autoscale；Online 不可 Scale-to-Zero
- Google Vertex AI：Autoscaling、Scale to Zero（Preview）、vLLM 相关指标
- 阿里云 PAI-EAS：水平/定时扩缩、缩 0、弹性资源池；ACK AHPA 智能预测
- 腾讯云 TI-ONE：定时 / HPA / 组合策略、Token 指标、PD 角色扩缩
- 华为云 ModelArts：CRON_HPA / METRIC_HPA
- 火山引擎：VKE IHPA；MLP 定时/指标扩缩；AI 云原生推理套件
- 百度千帆：专属推理服务扩缩容 API/控制台
