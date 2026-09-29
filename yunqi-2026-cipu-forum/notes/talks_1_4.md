# 云栖大会 2026 · CIPU 论坛 Talk 1–4 结构化笔记

来源回放：https://yunqi.aliyun.com/2026/session?agendaId=164  
论坛主题：Agentic AI 时代的算力与存储服务器革新

---

## Talk 1: 云基础设施处理器 CIPU 技术深度解读

- Speakers: 杨航（阿里云智能集团 资深技术专家 / Principal Engineer）
- Video range: 约 `00:02:00` – `00:33:00`（截图目录 `01-cipu/`：`t00-02-07` → `t00-31-40`；`t00-33-20` 起为论坛转场）

### Summary

本场由杨航系统解读 CIPU（Cloud Infrastructure Processor）在 AI 云基础设施中的定位与技术演进。演讲开篇重申云计算核心价值主张——弹性、多租、安全、稳定、性能、成本，并强调「多租安全隔离仍然是底线」。CIPU 的业务定位是把存储与网络 IO（原 Dom0）从 Host OS 剥离到专用硬件，实现多租安全隔离增强与数据访问硬件加速。CIPU 已完成五代演进，网络从 2×10GbE 提升到第五代的 2×200GbE，并逐步叠加 VPC/EBS/eRDMA/CPFS 硬件加速与 TPM 可信计算。面对 AI Agent、推理与训练场景，演讲分别展开：Agent 弹性裸金属与 MicroVM 强隔离、GPU 裸金属多租安全八项底线、推理侧 VSC/NVMe KV/OSS GDS over eRDMA 存储路径，以及训练侧 RC 兼容、SACK 选择性重传、多路径报文喷洒与 Over VPC。核心主张是：安全和性能是 AI 云基础设施的核心业务诉求，CIPU 以硬件直通与卸载把多租隔离与数据面加速做成平台能力。

### Key points

- CIPU 定位：多租安全隔离增强（安全）+ 数据访问硬件加速（性能）。
- 传统 KVM：存储/网络 IO 在 Host OS Dom0；CIPU 虚拟化：Dom0 下沉到 CIPU，Host 侧为 CIPU Hypervisor，提供硬件直通 IO 虚拟化。
- 五代演进：2017 第一代 2×10GbE（弹性裸金属、安全容器）→ 2018 2×25GbE（裸金属与 VM 并池）→ 2019 2×50GbE（VPC 硬件加速）→ 2022 2×100GbE（弹性 RDMA、EBS 硬件加速）→ 2024 第五代 2×200GbE（CPFS 硬件加速、EBS/VPC 数据加解密、TPM）。
- AI 安全语境引用：2026/07/21 OpenAI 相关「AI 智能体沙箱逃逸」；2026/08/30 SemiAnalysis「Most Neoclouds Suck At Security」。
- 能耗视角：相对 TPUv4 7nm，DRAM 访问远贵于算力（如 DRAM ~1300 pJ/op vs Int Add ~0.03 pJ/op），瓶颈转向内存墙与跨服务器互联/存储访问。
- Agent 基础设施：一方 AI Sandbox（E2B/K8S API）与第三方 Firecracker/gVisor/Kata 等并池；底层弹性裸金属 + CIPU DPU 模式（设备虚拟化、控制面吞吐/时延优化、IO 休眠唤醒）。
- GPU 裸金属多租八项底线：Host BIOS/BMC 固件安全、BMC 带外/带内隔离、多租切换时 Host DDR 与 GPU memory 重置、DPU/CIPU 安全域与软件升级隔离、TPM 固件可信。
- 推理存储三条路径：① VSC（CPFS EFC client → VSC Agent）；② NVMe KV Command Set（KVCache store Agent）；③ OSS GDS over eRDMA（宣称全球首个 overlay RDMA 穿透云 LB）。
- 训练网络：NCCL/IBGDA/deep-ep 等 RC 生态兼容、应用零改动；SACK 在 5% 丢包下约 90% goodput（相对 Go-back-N）；多路径报文喷洒缓解大象流 ECMP hash 冲突、有效带宽约 +60%；Over VPC 多租隔离 + 柔性组网。
- 大模型权重等高价值资产的多租安全隔离被定义为「严肃云厂商的业务红线」。

### Sections

#### 1. 云计算核心价值与 CIPU 业务定位
- 六大价值：弹性、多租、安全、稳定、性能、成本；弹性+多租是云计算业务定义，安全等是计算价值主张。
- 从传统 KVM Dom0 卸载到 CIPU：Management / VPC / EBS / CPFS / eRDMA / Local disks。

#### 2. CIPU 五代演进
- 始终围绕云计算核心业务价值迭代带宽与卸载能力。
- 第五代重点：CPFS 加速、EBS/VPC 加解密、TPM 可信计算、2×200GbE。

#### 3. AI 基础设施的安全与性能挑战
- Neocloud 安全短板与 Agent 沙箱逃逸事件作为问题背景。
- 「算力廉价、数据访问昂贵」→ 内存墙 + 互联/存储成为关键路径。

#### 4. 面向 AI Agent：弹性与安全
- 一方与三方 sandbox 并池；MicroVM 强隔离；CIPU DPU 模式支撑控制面与设备虚拟化。

#### 5. 面向 GPU 裸金属：多租安全底线
- BIOS/BMC/DDR/GPU memory/DPU/TPM 八项硬要求，针对 neocloud 常见漏洞面。

#### 6. 面向推理：高性能存储
- VSC、NVMe KV、OSS GDS over eRDMA 三类多租高性能访问通道。

#### 7. 面向训练：高性能网络
- RC 兼容、SACK、多路径喷洒、Over VPC 四项网络深化优化。

### Recommended evidence screenshots

| 文件 | 内容说明 | 关键主张 |
|------|----------|----------|
| `t00-03-20.png` / `t00-04-10.png` | 标题页：CIPU 技术深度解读 | CIPU 支撑 AI Agent / 推理 / 训练等 AI infra |
| `t00-07-30.png` | 云计算核心价值六要素 | 无多租安全隔离则其他业务价值归零 |
| `t00-08-20.png` | 传统 KVM vs CIPU 虚拟化架构对比 | Dom0 下沉 CIPU，硬件直通 IO + 数据访问加速 |
| `t00-10-50.png` / `t00-11-40.png` | CIPU 五代演进时间线 | 第五代 2×200GbE + CPFS/加密/TPM |
| `t00-14-10.png` / `t00-15-00.png` | 安全事件 + Energy per Operation 图 | 数据访问远贵于计算；瓶颈在内存墙与互联 |
| `t00-18-20.png` | Agent sandbox 一方/三方并池架构 | CIPU DPU 模式支撑弹性并池与 MicroVM 隔离 |
| `t00-20-50.png` / `t00-21-40.png` | GPU 裸金属多租安全八项清单 | 大模型权重安全是云厂商业务红线 |
| `t00-24-10.png` / `t00-25-00.png` | VSC / NVMe KV / OSS GDS over eRDMA | 推理 KVCache 与模型加载的多租高性能通道 |
| `t00-28-20.png` / `t00-30-50.png` | 训练网络四项优化 | SACK 5%丢包 90% goodput；喷洒 +60% 有效带宽 |

### Takeaways

1. CIPU 是阿里云把「多租隔离」和「IO/数据访问加速」沉淀到硬件的主路径，而非单纯带宽升级。
2. 对 AI Agent/GPU 裸金属，安全底线被抬到固件、BMC、内存重置与 DPU 域隔离层面。
3. 推理侧把 KVCache/CPFS/OSS 做成 CIPU 上的多租高速通道；训练侧把 RDMA 可靠性与 ECMP 冲突做成硬件/协议能力。
4. 第五代 CIPU（2×200GbE + CPFS + 加解密 + TPM）是当前对标 AI infra 的硬件基线。
5. 叙事上明确对标 neocloud 安全不足，把严肃云的「多租安全」作为差异化主张。

---

## Talk 2: Agentic AI 时代，RISC-V CPU 的机遇、创新和实践

- Speakers: 傅晶晶（达摩院 RISC-V 资深技术专家 / RISC-V Principal Engineer, DAMO Academy）
- Video range: 约 `00:34:00` – `01:02:00`（截图目录 `02-riscv/`：`t00-34-20` → `t01-01-40`）

### Summary

傅晶晶从 Agentic AI 工作负载出发，论证 CPU 正从「配角」回到系统吞吐与体验的关键路径。演讲对比 Coding Agent 与 Deep Research Agent：前者工具执行与调度占大量 CPU 时间，后者长链路探索带来海量 Token 与高 I/O 压力。配比上，从生成式 AI 时代 CPU:GPU≈1:8（GPU 主导）转向 Agentic AI 的约 1:1～1:2，每 GW 数据中心 CPU 核数需求约 4×，CPU 成本占比由约 15% 升至 40%+。RISC-V 的结构性机会来自开放 ISA、模块化扩展、软硬协同与生态共建。创新方向包括高性能控制流核心、长上下文内存系统、数据搬运一等公民、开放异构互联与安全隔离。产品落地以玄铁 C950 为样板：RVA23.1、8 发射、>3GHz、SPECint2006 70+，并集成 Titan（RVV1.0）4K 超宽向量引擎与 Pulsar 矩阵扩展（单核 FP4 突破 8TFLOPS、4096-bit Tensor Cache）。最后给出 Coding Agent 端到端路径、芯片到系统六步落地路线，以及「云芯协同」下达摩院玄铁与阿里云/CIPU 的闭环协作。

### Key points

- 目录三问：为何是 CPU 架构拐点；为何 RISC-V 有结构性机会；玄铁如何与阿里云把机会兑现为产品（C950）。
- Coding Agent：Token 放大 10–15×；上下文约 15K–156K；工具调用 10–30 次；系统协同 GPU 35–60%、CPU 30–55%。
- Deep Research Agent：50–200 子步骤；单步 5K–20K Token；总 Token 约 0.25M–4M；检索/阅读/验证 I/O 压力高。
- Agent 消耗 ≈ Σ(输入上下文 + 输出 + 工具结果 + 重试)。
- CPU:GPU 从约 1:8 → 1:1～1:2；每 GW CPU 核数需求约 4×（TrendForce）。
- CPU 五个新角色：编排器、数据搬运枢纽、隔离边界、异构协同控制面、软件生态承载层。
- RISC-V 四窗口：开放 ISA、模块化扩展、软硬协同、生态共建（从「替代叙事」转向「速度叙事」）。
- 五创新方向：高性能控制流；长上下文内存（面向 KVCache/RAG）；Load-Store 与 DMA 融合；CPU/GPU/DPU/NIC 开放互联；CFI/TEE/机密计算与 I/O 隔离。
- 玄铁 C950：RVA23.1、8-issue、>3GHz、SPECint2006 70+；Vector/Matrix 进入 CPU 主线。
- Titan（RVV1.0）4K 超宽向量 + Pulsar 矩阵（FP4/FP8/MXFP 等，单核 FP4 >8TFLOPS，UMA，4096-bit Tensor Cache）。
- Coding Agent 六步路径：任务解析 → 上下文/RAG → 补丁生成 → 沙箱测试 → 失败重试 → RDMA 服务返回。
- 云芯协同五步：云场景定义 → 玄铁协同设计 → CIPU 与服务器创新 → 标杆验证 → 生态联合适配。

### Sections

#### 1. 为什么现在是 CPU 架构拐点
- Agentic AI 把单次推理变成持续规划、工具调用、验证与迭代。
- Coding / Deep Research 两类负载量化特征；CPU:GPU 配比重构。

#### 2. CPU 在 Agentic AI 的五个新角色
- Orchestrator / Data Mover / Security Boundary / Heterogeneous Control Plane / Software Anchor。

#### 3. 为什么 RISC-V 具备结构性机会
- 开放 ISA + 模块化扩展吸收不确定负载；软硬全栈闭环；生态复利。

#### 4. 五个创新方向
- 控制流、长上下文内存、数据搬运、异构互联、安全隔离，从点状优化走向系统级协同。

#### 5. 玄铁 C950 样板实践
- 服务器软件兼容基线 RVA23.1；宽发射乱序；向量/矩阵原生进入主线。
- Titan + Pulsar + 统一编址：少搬运、少等待、低切换。

#### 6. 实践路径与云芯协同
- Coding Agent 端到端；芯片→编译器→运行时→云原生安全→基准→参考设计闭环。
- 达摩院提供 RISC-V 底座，阿里云提供场景与规格牵引，经 CIPU/服务器创新落地。

### Recommended evidence screenshots

| 文件 | 内容说明 | 关键主张 |
|------|----------|----------|
| `t00-35-50.png` | 标题页 | Agentic AI 时代 RISC-V 的机遇、创新与实践 |
| `t00-36-40.png` | 目录三部分 | C950 面向旗舰性能与原生 AI 融合 |
| `t00-39-10.png` / `t00-40-00.png` | Coding vs Deep Research Agent 负载特征 | Agent 消耗公式；CPU 占比显著回升 |
| `t00-42-30.png` | CPU:GPU 配比重构 | 1:8→1:1～1:2；每 GW CPU 核数 4× |
| `t00-43-20.png` | CPU 五个新角色 | 编排/搬运/隔离/异构控制面/软件生态 |
| `t00-45-50.png` | 为何 RISC-V 适合 Agentic AI | 开放 ISA、模块化、软硬协同、生态共建 |
| `t00-46-40.png` | 五个创新方向 | 长上下文内存面向 KVCache/RAG |
| `t00-49-10.png` / `t00-50-00.png` | 玄铁 C950 规格卡 | RVA23.1、8 发射、>3GHz、SPECint2006 70+ |
| `t00-52-30.png` / `t00-53-20.png` | Titan + Pulsar + 统一编址 | 单核 FP4 >8TFLOPS；4096-bit Tensor Cache |
| `t00-55-50.png` | Coding Agent 端到端六步 | CPU/Vector/Matrix/安全/RDMA 分工 |
| `t00-59-10.png` / `t01-00-00.png` | 云芯协同五步 | 玄铁底座 + 阿里云场景牵引 + CIPU 协同 |

### Takeaways

1. Agentic AI 使 CPU 重回吞吐关键路径，配比与成本结构发生结构性变化。
2. RISC-V 的价值主张从「替代 x86」转向「更快共设 AI 原生算子/内存语义」。
3. C950 以宽发射 + Titan/Pulsar 把检索、向量与张量算子拉回通用服务器流水线。
4. 落地强调全栈闭环（编译器/运行时/安全/基准/参考设计），而非单点芯片指标。
5. 与阿里云、CIPU 的「云芯协同」是把 RISC-V 兑现为云产品的组织与工程机制。

---

## Talk 3: Infini-AIOps / 智算集群运维智能体

- Speakers: 吴保东（无问芯穹技术副总裁 / Vice President of Technology, Infinigence AI）
- Video range: 约 `01:02:00` – `01:29:00`（截图目录 `03-aiops/`：`t01-02-40` → `t01-28-20`）

### Summary

吴保东从智算集群人工运维的痛点切入：故障影响面大、问题分散、人效低、排查难；样例数据约 1519 个运维问题、平均处理 1.2 小时，传统链路从告警到手工恢复可达数小时至数十小时，告警收敛率约 60–70%、诊断准确率 <60%。核心矛盾是复杂异构基础设施与人工运维模式不匹配。现有通用 Benchmark（MMLU/GAIA/SWE-Bench）与 Agent Eval（LangSmith/DeepEval）无法覆盖 Kubernetes/Prometheus 真实交互与 GPU 集群故障处置。为此提出评测体系：`aiops-data`（历史工单 1600+ 与海量告警清洗合成）与 `aiops-chaos`（控制面 aemu + 执行面 executor pod，劫持 nvml 模拟 GPU 故障、RDMA hottrash 等）。评测显示瓶颈已从「会不会诊断」转向「稳定推理与安全执行」。Infini-AIOps 架构分层为智能体运行时（Skills/Memory/知识库）、可信沙箱（GPU 透传与审计）、工具层与节点层。实测工单处理时长从峰值 5.5 小时降至 0.47 小时（约 -91%），人效近 12×。未来规划聚焦更高仿真度故障环境、数据合成、多模态交互与 Harness 形式化优化。

### Key points

- 人工运维问题：故障影响大、问题分散、人效低、排查难；约 1519 问题 / 平均 1.2h。
- 传统链路：告警→发现→人工判断→跨团队排查→手工恢复；周期数小时～数十小时。
- 技术挑战：告警噪声高；缺跨集群统一视图；GPU 专属诊断不足；诊断准确率 <60%。
- 组织挑战：技能门槛高、依赖值守、知识难沉淀；新人培养 >1 个月。
- 评测缺口：通用 Benchmark/Agent Eval 缺真实运维场景与 K8s/Prometheus 交互；GPU 集群无专用运维智能体评测标准。
- `aiops-data`：2024–2026 工单 1600+ + 线上告警；过滤/去重/LLM 0–10 打分/脱敏；故障构造 + LLM 辅助 + 人工复核。
- `aiops-chaos`：K8s 控制面 `aemu` + GPU 节点 `executor pod`；nvml 劫持模拟显存/温度/频率/风扇异常；RDMA 链路/交换机故障注入与恢复。
- 失败模式：任务稳定性不足、推理链质量差、决策执行不安全。
- 优秀运维 Agent 四要素：Harness 兜底、高信噪比知识、警惕 Reward Hack 并强化过程监管、可信可控沙箱。
- Infini-AIOps：Skills（GPU 故障定位/性能分析）+ 知识库 + 沙箱 GPU 透传 + 告警/日志/运维工具 + 节点驱动与健康自愈。
- 实测：处理时长 5.5h → 0.47h（约 -91%），人效约 12×；峰值工单约 262 仍可提升效率。
- 未来：提升故障仿真可信度、自动合成高价值数据、多模态（监控大盘/截图）、Harness 结构与形式化推导 + 在线强化学习。

### Sections

#### 1. 人工运维模式的分析与挑战
- 量化痛点与核心矛盾：异构智算设施 vs 人工链路。

#### 2. 运维智能体评测挑战
- 通用 Benchmark / Agent Eval / GPU 运维三方均缺统一可复现标准。

#### 3. aiops-data：评测数据集
- 工单与告警双轨清洗合成，强调真实、规范、可复现。

#### 4. aiops-chaos：故障模拟器
- 控制面/执行面协同；GPU（nvml）与 RDMA 软硬件故障自动注入与恢复。

#### 5. 评测结论与构建要点
- 瓶颈转向稳定推理与安全执行；Harness / 知识 / 过程监管 / 沙箱。

#### 6. Infini-AIOps 架构与实测
- Skills–Sandbox–Tools–Node 四层；工单时长与人效量化收益。

#### 7. 未来规划
- 工程优化（仿真、数据、多模态）+ Harness 探索（结构、记忆/RL、形式化）。

### Recommended evidence screenshots

| 文件 | 内容说明 | 关键主张 |
|------|----------|----------|
| `t01-02-40.png` | 嘉宾介绍页 | 吴保东 / 无问芯穹技术副总裁 |
| `t01-04-10.png` / `t01-05-00.png` | 人工运维挑战总览 | 1519 问题、1.2h；诊断准确率 <60% |
| `t01-07-30.png` / `t01-08-20.png` | 评测挑战三柱 | 缺统一真实可复现运维智能体评测标准 |
| `t01-10-50.png` / `t01-11-40.png` | aiops-data 流水线 | 1600+ 工单 + 告警 → 故障构造数据集 |
| `t01-14-10.png` / `t01-15-00.png` | aiops-chaos 架构 | aemu + executor；nvml/RDMA 故障注入 |
| `t01-17-30.png` / `t01-18-20.png` | 失败模式与优秀 Agent 关键 | 瓶颈=稳定推理+安全执行 |
| `t01-20-50.png` / `t01-21-40.png` | Infini-AIOps 技术架构图 | Skills/Memory + 可信沙箱 GPU 透传 |
| `t01-24-10.png` / `t01-25-00.png` | Demo 与实测曲线 | 5.5h→0.47h（-91%），人效 ~12× |
| `t01-27-30.png` / `t01-28-20.png` | 未来规划 | Harness 形式化优化，非盲目 LLM 调参 |

### Takeaways

1. 智算运维智能体首先缺的是「真实可复现评测」，而非再堆一个通用 Agent benchmark。
2. `aiops-data` + `aiops-chaos` 把工单/告警与 GPU/RDMA 故障注入做成评测基础设施。
3. 生产可用的关键从「诊断对不对」转为「跑得稳、执行安全、可审计」。
4. Infini-AIOps 用 Skills/知识库 + 可信沙箱 + 工具/节点适配把运维经验工程化。
5. 实测约 91% 处理时长下降与近 12× 人效，说明规模化工单下智能运维有明确业务价值。

---

## Talk 4: KVCache 池化·管理·仿真与软硬结合推理基础设施

- Speakers:
  - 王正恒（阿里云智能集团高级技术专家 / 阿里云数据库高级技术专家）— 池化·管理·仿真
  - 徐国强（阿里云服务器研发高级技术专家）— 软硬结合推理基础设施
- Video range: 约 `01:30:00` – `02:20:00+`（截图目录 `04-kvcache/`：`t01-30-40` → `t02-19-10`）

### Summary

本场由王正恒与徐国强接力，讨论如何把 KVCache 从「显存开销/计算中间态」升级为「可复用的推理资产」并落到基础设施层。王正恒部分阐述三层跃迁：跨请求前缀命中跳过 Prefill、Agentic 多轮 KV 持久、跨实例共享 KV 池；架构上以 Tair KVCM 做控制面全局放置与生命周期管理，数据面经 Router 的 KV Aware Routing 进入 LLM Engine，再对接 Tair MemPool（G2.5，RDMA 跨节点共享，DRAM/SSD 分级）。HiSim + NVIDIA AIConfigurator 把多级配置经验转为可量化的吞吐/SLO/成本决策（仿真误差宣称 <3% 量级），并强调存储介质需满足带宽-容量解耦、弹性伸缩、低延迟高持续带宽、耐久匹配与 TCO（宣称可测 TCO 降幅超 80%）。徐国强部分给出 G1–G4 分层存储定义：G1 HBM、G1.5 Scaleup（AMES/HBF/UMX）、G2 DRAM、G2.5 CXL/RDMA Memory Pool、G3 本地 SSD、G3.5 分布式/EBoF、G4 对象/文件。磐久 UMX（Unified Memory Extension）以 Alink Scale Up Fabric（UALink+CXL，Load/Store 语义）打通 GPU/CPU 与 DRAM/SCM/SSD 池，目标场景含超长 KVCache。Tair Memory Pool 实测 KVCache offloading 吞吐 +50%+、TTFT -30%；G3/G3.5 给出 vCNS-FS / KV Engine + EBoF（DPU/TLC/QLC/FDP）方案，并以 HiSim+Optimizer 做 SSD 选型。最后以「模型-软件-硬件」L1–L4 全景收束，强调与 CIPU 等纵向全栈协同。

### Key points

- KVCache 定义：Prefill 写入、Decode 逐步读取、分块存储管理；目标是以读代算、跨请求复用、冲破单机 HBM。
- 三跃迁：① 前缀命中跳过 Prefill 降 TTFT；② Agentic 多轮 KV 持久；③ 跨实例池化到网络存储，容量独立扩展。
- 控制面 Tair KVCM：meta service、统一分配、多级后端、cache strategy（workload/TTL/weight）、HiSim 仿真服务。
- 数据面：Requests → KV Aware Router → LLM Engine Connector → Tair MemPool（RDMA，乱序加速，节点间共享 KV）。
- KVCM 分层：运维平台 / 双实例高可用 Manager（元数据、调度、心跳）/ K8s Operator 多存储集群（FlexLightStore、MooncakeStore、Pangu、TairMempool 等）。
- HiSim + AIConfigurator：端到端仿真 TTFT/TPOT；Pareto 选配写回 GPU Workers；高保真仿真→配置决策→生产回流。
- 存储介质五需求：带宽-容量解耦、弹性伸缩、低延迟+高持续带宽、耐久-负载匹配（DWPD）、最优 Token 成本 TCO（宣称 >80% 降幅）。
- 分层：G1 HBM4/4e（~20TB/s+，~500ns，100GB+）→ G1.5 AMES/HBF → G2 DRAM → G2.5 CXL/RDMA 池 → G3 SSD → G3.5 EBoF/vCNS → G4 对象/文件。
- AMES：约 3.2TB/s/tray（超节点可至 25.6TB/s+），延迟 <2μs，容量 8TB+/tray（节点可达 128TB+ 量级表述）。
- 磐久 UMX：互连芯片 + 介质 + 软件；Alink Scale Up（UALink+CXL）；纳秒级接入，消除 Agent 时代「存储墙」；场景含极速推理、Agent 记忆、超长 KVCache。
- Tair Memory Pool：全局地址管理、多网卡传输效率 93%+；KVCache offload 吞吐 +50%+、TTFT -30%；支持 UMX（NVLink/UALink/CXL）与多 XPU。
- Tair Memory Pool 2.0：去中心化、统一编址、弹性、多租；L1–L4 介质/传输抽象（RDMA/TCP 等）+ Meta Service。
- G3/G3.5：vCNS-FS 文件语义微缓存 + KV Engine 语义缓存；EBoF Cache Box/Server（DPU，TLC/QLC/SCM/FDP）。
- SSD 选型：HiSim（在线可行性/带宽）+ Optimizer（容量/写入）；约束取带宽、容量、寿命三者最大值；SLO 如 Mean TPOT < 10s。
- 全景 L1 API 服务 → L2 推理引擎（vLLM 等）→ L3 KV 管理加速 → L4 硬件（含 CIPU）；强调纵向全栈与模型-Infra 协同。

### Sections

#### 1. 从显存开销到可复用推理资产（王正恒）
- Prefill/Decode 与 KV 资源化；跨请求、跨轮次、跨实例三层复用。

#### 2. 阿里云 KVCache 架构：引擎内 → 全局池化
- Tair KVCM 控制面 + Tair MemPool 数据面 + KV Aware Routing。

#### 3. 全局放置、生命周期与仿真决策
- 存算分离与多后端；HiSim × NVIDIA AIConfigurator × Pareto/SLO。

#### 4. 存储介质需求
- 解耦、弹性、延迟/带宽、DWPD 匹配、Token 级 TCO。

#### 5. 分层存储定义与技术方向（徐国强）
- G1–G4 栈；G1.5 AMES/HBF 与 G2.5 CXL/RDMA 作为关键桥接层。

#### 6. 磐久 UMX 与 Tair Memory Pool
- Scale Up 总线级统一内存扩展；实测吞吐/TTFT；MemPool 2.0 架构特性。

#### 7. G3/G3.5 软硬结合与 SSD 选型
- vCNS-FS / KV Engine / EBoF；HiSim+Optimizer 决策链路。

#### 8. KVCache 全景图
- 模型–软件–硬件 L1–L4 协同，呼应 CIPU 等基础设施。

### Recommended evidence screenshots

| 文件 | 内容说明 | 关键主张 |
|------|----------|----------|
| `t01-30-40.png` | 王正恒嘉宾介绍 | 阿里云智能集团高级技术专家 |
| `t01-32-30.png` / `t01-33-20.png` | KVCache：从显存开销到可复用推理资产 | 跨请求 / 多轮持久 / 跨实例池化 |
| `t01-35-50.png` | 全局池化系统协同架构 | Tair KVCM + KV Aware Routing + Tair MemPool RDMA |
| `t01-36-40.png` / `t01-39-10.png` | Tair KVCM 全局放置与生命周期 | 存算分离；多后端含 Pangu/TairMempool |
| `t01-40-00.png` / `t01-42-30.png` | HiSim × NVIDIA × 服务器仿真优化 | 仿真驱动配置；Pareto/SLO 写回 |
| `t01-43-20.png` | KVCache 对存储介质五需求 | TCO 可测降幅超 80%（幻灯主张） |
| `t01-45-50.png` / `t01-46-40.png` | 双讲者目录 | 王正恒池化管理仿真；徐国强软硬结合 |
| `t01-49-10.png` / `t01-50-00.png` | G1–G4 分层存储定义表 | HBM/AMES/CXL/SSD/EBoF 指标栈 |
| `t01-52-30.png` / `t01-53-20.png` | 磐久 UMX / Alink Scale Up | UALink+CXL；超长 KVCache 目标场景 |
| `t01-59-10.png` | Tair Memory Pool G2/G2.5 | 吞吐 +50%+；TTFT -30%；传输效率 93%+ |
| `t02-02-30.png` | Tair Memory Pool 2.0 架构 | 统一编址、去中心化、多租、弹性 |
| `t02-05-50.png` / `t02-09-10.png` | G3/G3.5 EBoF + vCNS/KV Engine | 文件语义与 KV 语义双路径；DPU/FDP |
| `t02-12-30.png` / `t02-15-50.png` | G3 SSD 选型 HiSim+Optimizer | 带宽/容量/寿命三约束取最大 |
| `t02-19-10.png` | KVCache 全景 L1–L4 | 模型-软件-硬件终极协同；含 CIPU |

### Takeaways

1. KVCache 正在从引擎内优化上升为可调度、可池化、可计量的推理基础设施资产。
2. Tair KVCM + MemPool + KV Aware Routing 构成「控制面策略 + 数据面 RDMA 共享」的系统闭环。
3. HiSim 把多级缓存配置从经验判断变成可量化的 SLO/成本 Pareto 决策。
4. 硬件侧用 G1.5 UMX/AMES 与 G2.5/G3/G3.5 池化存储突破 HBM 墙，服务超长上下文与 Agent 多轮。
5. 最终竞争力取决于模型、推理引擎、KV 中间件与 CIPU/互联/存储的纵向协同，而非单一层优化。
