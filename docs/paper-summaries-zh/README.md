# 三篇 LLM 路由论文：中文摘要索引与对照

本目录为三篇公开论文的**详细中文解读摘要**（非全文翻译）。原文请以 arXiv PDF 为准。

| 文件 | 论文 | arXiv |
|------|------|-------|
| [01-frugalgpt.md](./01-frugalgpt.md) | FrugalGPT（Stanford, 2023） | [2305.05176](https://arxiv.org/abs/2305.05176) |
| [02-routellm.md](./02-routellm.md) | RouteLLM（Berkeley et al., 2024） | [2406.18665](https://arxiv.org/abs/2406.18665) |
| [03-lodestar.md](./03-lodestar.md) | Lodestar（UIUC / ByteDance, 2026） | [2606.00946](https://arxiv.org/abs/2606.00946) |

---

## 一眼定位

| 论文 | 一句话 |
|------|--------|
| **FrugalGPT** | 预算内调用多家 API：生成后打分，不够再升级（级联） |
| **RouteLLM** | 生成前只选一次强/弱模型，用偏好数据降本保质 |
| **Lodestar** | 同模型多 GPU 实例间选 Pod，在线学 TTFT 最优路由 |

---

## 核心维度对照

| 维度 | FrugalGPT | RouteLLM | Lodestar |
|------|-----------|----------|----------|
| **路由对象** | 哪个 LLM API | 强模型 vs 弱模型 | 哪个 GPU 实例 |
| **系统层级** | API / 应用编排 | 模型选择（语义路由） | Serving 网关 |
| **主目标** | 准确率 ↑ + 成本 ↓ | 质量≈强模型 + 成本 ↓ | TTFT ↓ |
| **决策时机** | 生成后打分，不够再升级 | 生成前一次定生死 | 请求到达时选实例 |
| **每请求调用** | 1…m（级联） | 固定 1 | 1（打到一个 Pod） |
| **学习信号** | 任务对错 + 预算约束 | 人类 / Judge 偏好 | 真实 TTFT |
| **学习方式** | 离线学 cascade / 阈值 | 离线训 router，可换模型对 | 在线持续学习 |
| **关键状态** | 几乎无（黑盒 API） | Query 语义难度 | KV / 队列 / prefill·decode / GPU |

---

## 决策时机 & 调用次数

| | FrugalGPT | RouteLLM | Lodestar |
|--|-----------|----------|----------|
| **何时决策** | 拿到 answer 后打分 | 调模型之前 | 进引擎之前 |
| **决策依据** | \((q,\hat{a})\) 可信度 | 仅 \(q\) 难度/可区分性 | \(q\) + 集群实时快照 |
| **能否纠错** | 能（后级可救） | 不能 | 不涉及模型对错 |
| **调用次数** | 1…m | 恒为 1 | 恒为 1（实例） |
| **延迟形态** | 可能串行累加 | 单次 + 极小路由开销 | 单次 + ~3–5 ms |

---

## 学习信号 & 学习方式

| | FrugalGPT | RouteLLM | Lodestar |
|--|-----------|----------|----------|
| **标签** | 答对/答错 | 强赢/平局/弱赢 | 测得的 TTFT |
| **优化** | max 准确率 s.t. 成本≤b | 学 \(P(\text{win}_s\|q)\)，α 控成本 | 学 −TTFT，选 argmax |
| **训练** | 离线固定 | 离线；线上调 α | 在线持续（~5 分钟可收敛） |
| **特有挑战** | cascade 搜索贵 | 偏好噪声、分布错位 | circular dependency |

---

## 关键状态

| 状态类型 | FrugalGPT | RouteLLM | Lodestar |
|----------|-----------|----------|----------|
| Query 难度 | 间接 | **核心** | 仅 input length |
| 模型输出 | **核心** | 不看 | 不看 |
| API 单价 | 看 | 隐含 | 不看 |
| Prefix/KV | 不看 | 不看 | **看** |
| 队列/运行中 | 不看 | 不看 | **看** |
| Prefill/Decode | 不看 | 不看 | **看** |
| GPU 显存/型号 | 不看 | 不看 | **看** |

---

## 如何组合

```text
用户 Query
    → FrugalGPT / RouteLLM   （选哪个模型：质量 vs 成本）
    → Lodestar               （选哪个 Pod：延迟 vs 负载/缓存）
    → 引擎内调度             （vLLM continuous batching 等）
```

| 你要优化… | 优先看 |
|-----------|--------|
| API 花钱与质量，可接受多跳 | FrugalGPT |
| API 花钱与质量，且要一次调用 | RouteLLM |
| 同模型多副本的 TTFT / 尾延迟 | Lodestar |
