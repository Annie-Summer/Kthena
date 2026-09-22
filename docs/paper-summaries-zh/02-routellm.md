# RouteLLM 详细中文摘要

- **原文**：Ong, Almahairi, Wu, Chiang, Wu, Gonzalez, Kadous, Stoica. *RouteLLM: Learning to Route LLMs with Preference Data.* arXiv:2406.18665, 2024（UC Berkeley / Anyscale / Canva）
- **对应章节**：下文用「§」标注原文结构
- **说明**：本文件为解读摘要，非全文翻译

---

## 1. 问题与动机（§1）

强模型效果好但贵，弱模型便宜但能力弱。全走强模型浪费，全走弱模型质量不够。

**LLM routing**：先经 router，再决定由哪个模型处理。理想 router 应满足：

1. 每 query **只调一个** LLM（相对 cascade/ensemble 更低延迟）
2. 能泛化到域外 query
3. 换 LLM 组合时尽量不重训

RouteLLM 聚焦 **二分类路由**：在强模型类 \(\mathcal{M}_{\text{strong}}\) 与弱模型类 \(\mathcal{M}_{\text{weak}}\) 之间选择。

---

## 2. 问题形式化（§3）

### 2.1 赢率预测 + 阈值

偏好数据：\(\mathcal{D}_{\text{pref}}=\{(q,l_{s,w})\}\)，\(l_{s,w}\in\{\text{win}_s,\text{tie},\text{win}_w\}\)。

1. 学赢率模型 \(P_{\theta}(\text{win}_s\mid q)\)
2. 用阈值 \(\alpha\in[0,1]\) 决策：

\[
R^{\alpha}(q)=
\begin{cases}
\mathcal{M}_{\text{weak}} & \text{if } P(\text{win}_s\mid q)<\alpha \\
\mathcal{M}_{\text{strong}} & \text{if } P(\text{win}_s\mid q)\ge\alpha
\end{cases}
\]

\(\alpha\) 越大越省钱；越小越偏质量。

### 2.2 评价指标（§3.2）

| 指标 | 含义 |
|------|------|
| \(c(M_R)\) | 打到强模型的请求比例（成本代理） |
| \(r(M_R)\) | 平均回答质量 |
| **PGR** | 相对弱模型，追回了多少「强弱质量差」 |
| **APGR** | 不同成本约束下 PGR 的平均（性价比曲线面积） |
| **CPT(x%)** | 要达到 x% 的 PGR，最少需要打给强模型多少比例 |

例：MT Bench 上 CPT(50%) 对应质量约达 GPT-4 的 95%。

---

## 3. 数据与增强（§4.1）

### 3.1 主数据：Chatbot Arena

约 80K 人类对战。按 Arena 榜单分数聚成 **10 个 tier**：

- **Strong**：前两档（Tier 0–1）
- **Weak**：第三档（Tier 2）

训练时 **丢掉回复正文**，只保留 query + 谁赢，以学习「问题可区分性」而非文风。

### 3.2 数据增强

| 增强 | 做法 | 作用 |
|------|------|------|
| \(\mathcal{D}_{\text{gold}}\) | MMLU 验证集，用标准答案对比强弱输出 | 提升 MMLU 等 OOD |
| \(\mathcal{D}_{\text{judge}}\) | 用 GPT-4 对 Nectar 等对话打偏好（约 12 万条） | 提升开放域 / GSM8K 等 |

结论：**训练分布越贴近评测/线上 query，router 越好**；可用 benchmark-dataset similarity score 定量解释。

---

## 4. 四种 Router（§4.2）

都在估同一件事：\(P(\text{win}_s\mid q)\)。

| 方法 | 思路 | 特点 |
|------|------|------|
| **Similarity-weighted ranking** | 找相似历史 query，Bradley-Terry 估强弱 | 无需训练，推理时求解；开销偏大 |
| **Matrix factorization** | 学 query/model 隐向量打分差 | 效果通常最好；部署开销小 |
| **BERT classifier** | 微调 BERT 分类头 | 数据少时弱，增强后变强 |
| **Causal LLM** | Llama-3-8B 指令式预测 win 标签 | 容量大；增强后在 GSM8K 等不错 |

评测主设定：Strong = `gpt-4-1106-preview`，Weak = Mixtral-8x7B；基线为同成本约束下的随机路由。

---

## 5. 主要实验结论（§5）

### 5.1 质量–成本

- MT Bench：增强后 matrix factorization 等可大幅降低 CPT；可达约 95% GPT-4 质量且显著少打 GPT-4
- MMLU / GSM8K：仅用 Arena 时接近随机；加上 gold/judge 增强后明显超过随机
- 相对纯 GPT-4，成本节省可达约 2× 以上（视目标质量与基准而定；公开材料亦常引用更高节省比例）

### 5.2 模型对可迁移（§5.2）

**不重训**，直接换：

- Claude 3 Opus / Sonnet
- Llama 3.1 70B / 8B

仍明显优于随机。说明学到的主要是 query 侧「难不难 / 强弱差距大不大」，而非绑定某两个具体模型。

### 5.3 路由开销（§5.5）

相对 GPT-4 生成成本，router 额外成本通常很小（文中最贵的 SW ranking 约不超过 GPT-4 成本的 0.4% 量级）。

---

## 6. 与相关工作的差别（§2）

| 工作 | 差别 |
|------|------|
| FrugalGPT / AutoMix | 常需多次调用；RouteLLM **固定一次** |
| LLM-Blender | 多模型生成再融合，延迟更高 |
| Hybrid-LLM / Zooter | 更偏合成标签或单一 BERT；RouteLLM 强调人类偏好、多种架构与 OOD |

---

## 7. 局限（§6）

- 主场景是 **二模型路由**；多模型路由仍是未来方向
- 真实业务分布若远离 Arena/基准，需要少量域内增强
- 没有「永远最好」的单一 router，需按延迟、成本、query 类型选择

---

## 8. 一句话

RouteLLM 用偏好数据离线训练轻量 router，在 **生成前** 判断「这个问题值不值得上强模型」，实现单次调用下的质量–成本可控折中，并具备跨模型对的迁移能力。
