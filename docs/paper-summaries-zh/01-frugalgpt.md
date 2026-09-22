# FrugalGPT 详细中文摘要

- **原文**：Chen, Zaharia, Zou. *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* arXiv:2305.05176, 2023（Stanford）
- **对应章节**：下文用「§」标注原文结构，便于对照 PDF
- **说明**：本文件为解读摘要，非全文翻译

---

## 1. 问题与动机（§1–§2）

商业 LLM API（GPT-4、ChatGPT、J1-Jumbo 等）价格差异可达约两个数量级。大规模调用最强模型成本很高：论文举例，小公司客服场景用 GPT-4 每月可能超过约 2 万美元。

**形式化目标**：在平均成本不超过预算 \(b\) 的约束下，最大化任务表现：

\[
\max_s\ \mathbb{E}[r(a,\hat{a}(s,q))]
\quad\text{s.t.}\quad
\mathbb{E}[c(s,q)] \le b
\]

策略空间很大：选什么 prompt、调用哪些 API、如何聚合回答等。

---

## 2. 三类降本策略（§3）

### 2.1 Prompt adaptation（改 prompt）

- **Prompt selection**：少放 in-context 例子，缩短计费输入
- **Query concatenation**：多个 query 拼进一次请求，共享同一段 prompt，减少重复 prompt 费用

### 2.2 LLM approximation（用便宜物近似贵模型）

- **Completion cache**：相似 query 直接复用缓存答案
- **Model fine-tuning**：用贵模型输出蒸馏/微调小模型，线上走小模型（常还能缩短 prompt、降低延迟）

### 2.3 LLM cascade（级联调用）— FrugalGPT 主实现

按顺序调用一串模型（通常由便宜到贵）：

1. 调用当前 API 得到回答 \(\hat{a}\)
2. 用 **generation scoring function** \(g(q,\hat{a})\) 打「可信度」
3. 若分数 ≥ 该层阈值 \(\tau_i\)，提前返回；否则问下一个模型

关键部件：

| 部件 | 作用 |
|------|------|
| Scoring function | 判断当前回答是否可靠（文中用 DistilBERT 回归） |
| LLM router | 学习调用顺序 \(\boldsymbol{L}\) 与各层阈值 \(\boldsymbol{\tau}\) |

优化问题本质是带预算约束的混合整数优化；作者用搜索空间剪枝 + 样本插值近似求解。

三类策略可组合（如同时做 prompt 选择与 cascade），但会增加训练计算成本。

---

## 3. 实验设置（§4）

- **API**：12 个商业 API（OpenAI / AI21 / Cohere / Textsynth / ForeFrontAI）
- **任务数据**：
  - HEADLINES（财经标题，金价涨跌）
  - OVERRULING（法律 overruling 判定）
  - COQA（阅读理解，改编为直接问答）
- **Cascade 长度**：实验中取 3
- **对比**：与各数据集上最优单模型 API 比较成本与准确率

---

## 4. 主要结论（§4）

### 4.1 案例（HEADLINES，预算约为 GPT-4 的 1/5）

学到的链：`GPT-J → J1-L → GPT-4`

- GPT-J 分数 > 0.96 则停
- 否则问 J1-L；分数 > 0.37 则停
- 否则上 GPT-4

结果：相对 GPT-4，成本约降 80%，准确率反而约高 1.5%（部分题便宜模型对、GPT-4 错）。

### 4.2 模型互补性（MPI）

**MPI(A,B)**：B 错而 A 对的比例。  
例如 HEADLINES 上，约 6% 样本 GPT-4 错，但 GPT-J / J1-L 等能对。说明「贵模型并不总是对」，级联可借多样性提点。

### 4.3 成本与准确率

| 数据集 | 达到最优单模型同等准确率时的成本节省 |
|--------|--------------------------------------|
| HEADLINES | 约 **98%** |
| OVERRULING | 约 **73%** |
| COQA | 约 **59%** |

同成本下，准确率最高可约 **+4%**。论文强调：价格排序并不固定（计费结构异构），更贵 API 有时反而更差，因此即使用户不限预算也应认真选 API。

---

## 5. 局限与展望（§5）

- 训练 cascade 需要 **同分布带标签样本**
- 学习本身有一次性 upfront 成本，适合线上 query 量远大于训练集的场景
- 级联可能多跳，延迟通常高于「只调一次模型」的路由
- 未系统实现 prompt adaptation / approximation 的全部组合
- 未来可纳入延迟、公平、隐私、环境影响等更多约束

---

## 6. 一句话

FrugalGPT 提出「预算内用 LLM」的框架，并用 **生成后打分的 API 级联** 证明：多数请求可早停在便宜模型，难题再升级，从而大幅降本，甚至因模型互补超过单用 GPT-4。
