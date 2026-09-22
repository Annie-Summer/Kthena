# Lodestar 详细中文摘要

- **原文**：Lim, Zhao, Godfrey, Shan, Xu, Xie. *Lodestar: An Online-Learning LLM Inference Router.* arXiv:2606.00946, 2026（UIUC / ByteDance）
- **对应章节**：下文用「§」标注原文结构
- **说明**：本文件为解读摘要，非全文翻译；代码基于 AIBrix 开源

---

## 1. 问题与动机（§1–§3）

这里的「路由」不是选 GPT-4 还是 Mixtral，而是：

> 同模型的多个 GPU 实例（K8s Pod）中，把请求打到哪一台？

难点：

1. 请求成本差异极大（输入长度、prefill/decode）
2. **KV cache / prefix 复用** 造成请求间强耦合
3. 延迟对负载、缓存、硬件是 **非线性联合** 关系
4. 手工启发式（least-request、prefix-aware）在不同 RPS / 前缀共享率下会失效甚至优劣反转
5. 离线训好的延迟预测器一上线就漂——存在 **circular dependency**：  
   路由策略 → 改变集群状态 → 改变延迟分布 → 再改变策略

因此需要 **数据驱动 + 在线学习** 的实例路由。

---

## 2. 方法概览（§4）

### 2.1 学习目标

对每个 (实例 \(i\), 请求) 预测 reward：

\[
y = -\text{TTFT}
\]

请求打到 \(\arg\max_i \hat{y}_i\)（预测 TTFT 最低的实例）。

为何用 TTFT：用户体感关键；TPOT/E2E 观测太晚，且强依赖未知 decode 长度，噪声大。

### 2.2 模型结构

- 共享参数的 **3 层 MLP（隐层 128）+ ReLU + dropout**
- **不输入 instance ID**（避免「认死某 Pod」导致流量震荡）
- 实例增减无需改网络结构（适合弹性扩缩）

线性回归同等特征下误差明显更大，说明映射本质非线性。

### 2.3 特征（§4.1）

| 类别 | 内容 | 作用 |
|------|------|------|
| 请求 | input token 长度 | prefill 量、新 KV |
| 缓存 | expected prefix KV hit ratio | 能跳过多少 prefill |
| 负载 | running / queued 请求数 | 算力与排队 |
| 相位 | inflight prefill / decode tokens | 算力墙 vs 带宽墙（分开） |
| 硬件 | GPU 显存利用率、GPU 型号 | 可调度性、异构 |

**刻意不用**：粗粒度 GPU util / SM / 带宽利用率（采样噪声大）。

### 2.4 Consistent hashing filtering（缓解贪心局限）

纯贪心可能全局挤爆共享 prefix 的 KV。当集群显存利用率过高时：

1. 用 consistent hashing（以共享 prefix 为 key）先筛 \(k\) 个候选实例
2. 再在候选内按预测 reward 贪心

用于抑制尾部 TTFT 尖峰（消融显示对 P99 帮助更大）。

---

## 3. 系统架构（§4.2–§4.4）

### 3.1 Stateful Gateway（Go）

- 每请求打集群快照、算 prefix hit、请求 Routing Service
- 后台刮取实例内部队列 / KV 利用率等（约 100ms）
- 维护全局 prefix 索引（radix tree）
- **失败回退**：Routing Service 超时/错误时用预计算的启发式，不增加失败路径延迟

### 3.2 Routing Service（Python，可跑在 GPU）

- 批量对 \(N\) 个实例做一次前向（输入形状 \([N,d]\)）
- 训练与推理异步隔离；新模型原子切换
- 约每 \(\theta=1000\) 个新样本重训

### 3.3 在线训练数据选择

| 池 | 作用 |
|----|------|
| FIFO（\|F\|=5000） | 近因：适应当前负载 |
| Replay（\|R\|=5000） | 多样性：用 gradient-coreset 保留难/多样样本 |

每轮用 \(\mathcal{F}\cup\mathcal{R}\)；避免「只看新数据遗忘」或「全历史拖慢且钝化」。

实现基于 **AIBrix**，云原生跑在 Kubernetes；与 vLLM 等引擎配合。

---

## 4. 实验结论（§5）

### 4.1 设置

- 同构：8×A30；异构：A30+V100 或 L20+A30 等
- 模型：Llama3-8B FP16，vLLM；workload：Mooncake（conversation / toolagent / synthetic）及不同 prefix sharing 合成负载
- 主基线：AIBrix 的 **Prefix-cache-and-load-aware**，以及 Prefix-cache、Mooncake 启发式、least-request 等

### 4.2 性能

相对 Prefix-cache-and-load-aware：

| 场景 | mean TTFT | P99 TTFT |
|------|-----------|----------|
| 总体平均 | 约 **1.41×** 更低 | 约 **1.47×** 更低 |
| 同构最好 | 最高约 **2.15×** | 最高约 **1.86×** |
| 异构最好 | 最高约 **4.38×** | 最高约 **4.42×** |

约 **5 分钟** 在线学习即可学出有效策略。  
异构收益更大：可从数据学到「某 GPU 无 prefix cache / 显存更小」等差异，无需手写规则。

### 4.3 适应性与环形依赖（§5.3）

- 前缀共享率从 5% 切到 50%：持续在线学习能跟上；中途冻结模型会明显变差
- 策略会改变 KV 在集群中的分布，再反馈影响延迟——验证 circular dependency 真实存在
- 纯离线模型部署后预测质量崩塌，不宜单独依赖

### 4.4 开销（§5.4）

关键路径路由开销约 **3–4.5 ms**，远小于节省的 TTFT；训练不堵推理热路径。

---

## 5. 与语义路由的关系（§6）

作者明确：FrugalGPT / RouteLLM 等 **semantic router** 选的是「哪个模型」；Lodestar 在模型选定之后，选「哪个实例」。二者 **正交**，可串联：

```text
RouteLLM/FrugalGPT（选模型） → Lodestar（选 Pod） → 引擎内调度
```

---

## 6. 一句话

Lodestar 是面向分布式 LLM Serving 的 **在线学习实例路由器**：用真实 TTFT 反馈与丰富运行时状态，持续学习「这个请求此刻打到哪台 GPU 最快」，在同构尤其是异构集群上显著优于手工 prefix/load 启发式。
