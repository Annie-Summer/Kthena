# 云栖 2026 CIPU 论坛 · Talks 5–8 结构化笔记

来源：`screenshots/05-storage` … `08-future`，辅以 `_intros/`、`_bounds/`、`_refine/` 关键帧。时间戳为论坛回放相对时间。

---

## Talk 5: 让 Token 快人一步：Agentic AI 时代的存储软硬协同之路

- **Speakers:** 常存银（阿里云智能集团 / 阿里云服务器研发 · 资深技术专家 / Principal Engineer）
- **Video range:** 约 `02:20:50` – `02:44:10`（下一段异构算力约 `02:45:00` 开场）
- **Summary (Chinese):**  
  常存银从训练/推理/Agentic 三阶段存储需求差异出发，论证“没有一套存储通吃”，必须以场景做软硬协同。随后系统介绍阿里云自研介质栈（AliSCM CXL 持久内存、PCM SSD、AliFlash V6 TLC / V5 QLC）与磐久服务器形态（高性能整机、大容量整机、EBOF 缓存服务器），并以 GPU 为中心给出六级分层与推理场景零拷贝异构方案（HBM→DRAM→SCM/PCM/TLC/QLC + RDMA/EBOF）。

### Key points
1. **三阶段需求不可通吃：** 训练要吞吐、推理要时延、Agentic 要记忆；按场景软硬协同是必然选择。
2. **训练：** 千亿参数场景顺序写 ≥20GB/s、集群聚合 TB/s；语料约 1.5 万亿 token / 60TB+，格式化与副本达 PB 级 → 高吞吐并行文件系统 + 高性能对象存储。
3. **推理：** 随机读 10–30GB/s、IOPS ≥200K、时延 <100μs；Llama70B/128K 单请求 KV ≈336GB → HBM–DRAM–SSD 分层卸载与预取。
4. **Agentic：** 混合读写并发、P99 <10ms、元数据高并发；容量百 PB–EB；长期记忆 / RAG / 多模态 → 弹性扩展 + 冷热分层。
5. **介质金字塔：** DRAM/HBM → SCM/PCM SSD → TLC/QLC SSD → CMR/SMR HDD → Tape；按数据温度智能升降温。
6. **AliSCM：** CXL.mem（64B load/store）+ CXL.io；~200ns 延迟、~20GB/s 吞吐；容量 256GB–1TB；掉电持久化，降低冷启动 TTFT 退化；国产 PCM 颗粒。
7. **PCM SSD（AliFlash-PCM）：** NVMe 原生；**100 DWPD**；无盘内 GC；读写延迟双位数 μs；面向推理热路径与 KVCache。
8. **AliFlash V6 TLC：** 国产企业级 **PCIe 6.0 / NVMe 2.3 / OCP 2.0**；顺序读 **28GB/s**、写 **22GB/s**；随机读 **7M IOPS**、写 **1000K**；4–32TB（E3.S/E1.S）；Host 协同 FDP，最多 **16 RUH**，WAF ≈1.0X。
9. **AliFlash V5 QLC：** PCIe 5.0 NVMe；**16–128TB** U.2；顺序读 14GB/s / 写 4GB/s；随机读 2400K IOPS、延迟 85μs；盘内 **pSLC+QLC** 可调比例；AI 数据湖冷数据底座。
10. **磐久存储服务器：** 飞天盘古底座，承载 EBS/CPFS/OSS/PolarDB/ODPS；高性能侧 400G 网络、QAT/DSA、CXL+PMEM、TLC+QLC；大容量侧单机 **34PB**、120 盘 JBOD、按需上电功耗优化约 **70%**、IO 双平面；兼容倚天 ARM / x86 / RISC-V。
11. **磐久 EBOF 缓存服务器（最新发布）：** 2U；多路 DPU/CIPU（Tb 级带宽卸载）；AliSCM 热层 + TLC/QLC 大容量；单机逾百 TB；Hardware As Service，按需挂载。
12. **推理异构方案：** GPU 节点（vLLM/SGLang/RTP-LLM + KV Connector）本地 SCM/PCM/TLC；RDMA Fabric 做 KV Offload/Reload 零拷贝；EBOF 侧 SCM热/TLC温/QLC冷 + FDP；全栈控制面含元数据、亲和调度、QoS、可观测与全局命名空间。

### Sections

#### 1. 议程与问题定义
- 五段结构：需求趋势 → 介质分层 → 自研部件（AliSCM/PCM/AliFlash）→ 自研服务器（EBOF / 磐久）→ GPU 中心软硬协同方案。
- 核心命题：按数据温度做层级智能调度，热数据预热、冷数据淘汰，提升 GPU 利用率。

#### 2. AI 三阶段存储需求
- **训练：** Checkpoint、语料加载、预处理；可靠优先。
- **推理：** KV Cache 分层卸载、Prefix 缓存、权重/镜像加载；时延 + TCO。
- **Agentic：** 长期记忆持久化、RAG 向量检索、多模态数据；容量 + 并发。

#### 3. 自研存储部件
- **AliSCM：** 填补 DRAM 与 SSD 空档；字节寻址、极速、更优 TCO、掉电持久、多场景（向量库/多模态/快速恢复）。
- **PCM SSD：** SCM 大容量延伸；ONFI→PCM 桥接；国产存储级 PCM。
- **AliFlash V6 TLC / V5 QLC：** 分别服务热温路径与海量冷语料/数据湖。

#### 4. 自研 AI 存储服务器
- 磐久高性能 / 大容量一体平台。
- EBOF：DPU/CIPU + SCM + AliFlash TLC/QLC 爆炸视图；SCM+QLC 按温度自动调度。

#### 5. 以 GPU 为中心的分层与推理方案
- **六级：** 机头 DRAM → CXL AliSCM → GPU 本地 TLC → 本地 PCM-SSD → PCIe Switch 下 AliSCM → 远端磐久 EBOF（SCM热 + TLC/QLC 温冷）。
- 软件：用户态零拷贝（GPUDirect Storage / RDMA）、本地 KV 引擎（一致性 Hash、多副本 RPC、多跳并行）、EBOF 热度感知 demote/promote 与多流隔离。

### Recommended evidence screenshots
| Filename | Caption | Note |
|---|---|---|
| `05-storage/t02-21-40.png` | 标题页：让 Token 快人一步… | 确认讲题与讲者职称 |
| `_intros/t02-22-30.png` | 目录五段 | 全讲结构纲要 |
| `05-storage/t02-23-20.png` | 训练/推理/Agentic 三阶段需求 | 含 20GB/s、336GB、P99<10ms 等数字 |
| `_refine/t02-26-40.png` | AI 场景存储介质分层金字塔 | DRAM→Tape 定位 |
| `05-storage/t02-28-20.png` | AliSCM 产品架构 | CXL / ~200ns / 256GB–1TB |
| `05-storage/t02-31-40.png` | PCM SSD | 100 DWPD、无 GC、μs 级延迟 |
| `_refine/t02-33-20.png` | AliFlash V6 TLC | PCIe 6.0、28/22GB/s、7M IOPS、FDP |
| `05-storage/t02-35-00.png` | AliFlash V5 QLC | 16–128TB、pSLC+QLC |
| `_bounds/t02-36-40.png` | 磐久存储服务器软硬一体 | 34PB、400G、倚天/x86/RISC-V |
| `05-storage/t02-38-20.png` | 磐久 EBOF 缓存服务器 | 最新发布；DPU/CIPU+SCM+Flash |
| `_bounds/t02-40-00.png` | GPU 中心六级分层 | 近 GPU 热 ↔ 远端池化 |
| `05-storage/t02-41-40.png` | 推理异构存储软硬协同方案 | vLLM/SGLang/RTP-LLM + EBOF/FDP |

### Takeaways
- 存储战略从“单一系统”转向**按 AI 阶段与数据温度定制的异构介质栈**。
- 自研关键路径是 **AliSCM（内存语义）+ PCM SSD（超耐久热路径）+ TLC/QLC（带宽/容量）+ 磐久/EBOF（池化）**，软件侧以零拷贝与热度调度闭环。
- 对 Agentic：强调记忆持久化与“停得久≠价值低”的前置问题（在 Talk 7 Agentic KV 中进一步展开）。

---

## Talk 6: 面向 Agentic 推理的异构算力软硬结合技术

- **Speakers:** 卢晓伟（资深技术专家；舞台画面可见右臂石膏固定）
- **Video range:** 约 `02:45:00` – `03:16:40`（过渡页“从体系到实践，再到未来”；Talk 7 约 `03:18` 开场）
- **Summary (Chinese):**  
  卢晓伟论证 Agentic 推理从固定计算图走向动态任务图后，系统效率成为上限；给出公式「系统级推理效率 = 芯片能力 × 调度效率 × 软硬件成熟度」。硬件侧介绍超节点演进与 **AI Infra 3.0 AL144**（相对 AL128：144 卡 Scale-up、750kW、TBP 3500W、二级光互联至万卡级 10368）。软件/工程侧推出 **震旦** 异构算力软硬件协同组件交付平台（五大能力中心 + 双主线交付），并以全生命周期压测、联合仿真实测、AI 集群诊断 / Profiling / 全链路智能诊断，形成仿真–评测–监控–诊断闭环。

### Key points
1. **Agentic 特征：** 长链路、动态分支、多工具调用；固定计算图 → 动态任务图；规划×工具×执行。
2. **三大抓手：** 多元芯片协同（CPU/GPU/NPU/专用加速器）→ 异构资源调度（任务感知/实时编排）→ 软件能力平台化（统一抽象/可观测）。
3. **超节点趋势：** Scale-up 域约 10× 增长：DGX A100(8) → H200(8) → GB200 NVL72(72) → Rubin NVL576(576)；演进轴：8 卡 PCIe → 8 卡 OAM → 16 卡一体机 → **128 卡超节点** → **千卡节点**。
4. **代表产品：** 阿里云磐久 **AL128/AL144**、NVIDIA GB200 NVL72、AMD Helios MI455X。
5. **大 EP 推理：** 实测性能提升 **>40%**；Agentic 低延迟场景优势更突出。
6. **AI Infra 3.0 AL144：** 训推一体；柜内铜互连·跨柜光扩展；兼容产业 GPU/CPU/**ALink Switch**；供电可靠性 **6 个 9**；芯片-节点-机柜三级漏液监测。
7. **相对 AL128：** 单柜一级 Scale-up max **144 卡（2×）**；单柜 **750kW（2.15×）**；GPU TBP **3500W（1.75×）**；并柜 **288**；二级光互联支持千卡/万卡（**10368**）。
8. **UAM 计算模块：** 喷射流高效微流道冷板、垂直供电、全液冷；配套 800V Cap Shelf / 800V PDB。
9. **磐久超节点结构演进：** HBM 年增约 3.6× vs 模型内存需求 16× → 缺口约 **4.4×**；趋势①异构超节点按 A/F（Attention/FFN，GPU vs LPU）分离；趋势②同构超节点用 TP/CP/EP/PP-DP 找 Scale-up sweet spot。
10. **震旦交付平台：** L1 五大能力中心（性能评测/镜像服务/仿真规划/算力资源/数据采集）→ L2 统一研发发布 → L3 组件化交付引擎（Profiler、质量检测、故障诊断、Benchmark、Fabric Manager + 算子/架构/系统仿真器）→ L4 容器镜像/组件包/仿真器/评测报告。
11. **质量闭环：** 实验室→工厂→IDC→线上四位一体压测；NCCL/DeepEP 等通信库覆盖；联合仿真（Roofline/MicroArch）与实测校准。
12. **诊断与 Profiling：** 自然语言驱动 Agent 规划测例；60+ 测例覆盖 GPU/CPU/内存/PCIe/存储/网络；指标采集 100+、假阳性 0%、假阴性 <1%；调度失败率降 60–70%；微秒级全栈 Timeline，无需改代码。

### Sections

#### 1. Agentic 对多元算力的新需求
- 系统效率 = 硬件 × 调度 × 软硬件成熟度。
- 按阶段匹配芯片、按负载编排、按系统优化软件平台。

#### 2. 服务器 → 超节点
- Scale-up 成为 AI Infra 标准形态；机柜级整合 Compute/Switch tray、散热、供电。
- 大 EP / Agentic 低延迟场景收益显著。

#### 3. AI Infra 3.0 AL144 与结构演进
- 开放、标准化、模块化；铜内光外扩展。
- 内存墙推动异构（A/F）与同构（并行策略）两条超节点路线。

#### 4. 震旦异构算力软硬件协同组件交付平台
- 面向多厂商、多架构 AI 芯片的统一交付与仿真。
- Mainline A：软硬件协同组件；Mainline B：算力仿真器。

#### 5. 工程闭环：压测 / 仿真 / 诊断 / Profiling
- 全生命周期质量数据驱动。
- AI 集群诊断分析平台：智能诊断 + 指标采集 + 性能分析。
- 全链路智能诊断平台：场景分析 Agent → 诊断引擎 → 分析 Agent → 诊断知识库。

#### 6. 过渡到后续议题
- 当前：异构超节点 + 全栈优化 + 智能闭环。
- 下一段：Agentic 推理全栈优化实战；再后：未来架构探索。

### Recommended evidence screenshots
| Filename | Caption | Note |
|---|---|---|
| `06-heterogeneous/t02-45-00.png` | 标题页：面向 Agentic 推理的异构算力… | 开场确认 |
| `06-heterogeneous/t02-47-30.png` | Agentic 对多元算力的新需求 | 核心结论公式 |
| `_intros/t02-51-40.png` | 服务器向超节点演进 | AL128/AL144、>40% EP |
| `06-heterogeneous/t02-53-20.png` | AI Infra 3.0 AL144 | 144 卡 / 750kW / 10368 |
| `06-heterogeneous/t03-00-00.png` | 磐久超节点结构性架构演进 | A/F 异构 vs 同构 sweet spot |
| `06-heterogeneous/t03-03-20.png` | 震旦异构算力交付平台 | 四大层 + 五大中心 |
| `_bounds/t03-08-20.png` | 联合仿真与实测 GPU 评估 | Roofline/MicroArch 闭环 |
| `06-heterogeneous/t03-10-00.png` | 全生命周期压测与质量分析 | 实验室→线上四场景 |
| `_bounds/t03-12-30.png` | AI 集群诊断分析平台 | Agent 诊断 + Profiling |
| `06-heterogeneous/t03-13-20.png` | 全链路智能诊断平台 | 60+ 测例、知识库 |
| `07-fullstack/t03-15-00.png` | 监控与 Profiling | 0% 假阳性、60–70% 调度失败下降 |
| `07-fullstack/t03-16-40.png` | 从体系到实践，再到未来 | Talk 6→7/8 过渡页 |

### Takeaways
- Agentic 把瓶颈从“单芯片峰值”推向**系统级协同**（芯片×调度×工程成熟度）。
- 硬件叙事中心是 **磐久超节点 AL144 + ALink + UAM 液冷供电**；软件叙事中心是 **震旦交付/仿真/诊断平台**。
- “智能闭环”（仿真→压测→监控→Agent 诊断）是规模化异构落地的工程底座，直接衔接下一段全栈优化实战。

---

## Talk 7: Agentic 时代 AI 推理软硬件结合全栈优化实战

- **Speakers:** 资彦义（阿里云智能集团 · 高级技术专家）；李陈浩文（阿里云智能集团 · 高级工程师）
- **Video range:** 约 `03:18:20` – `03:48:20`（Talk 8 主持人过渡约 `03:49:10`，李文韬约 `03:50:00` 开讲）
- **Summary (Chinese):**  
  两位讲者以可复现 **Dev Loop**（目标→评测→下钻 Profiler/Trace→定位→优化→回归）组织全栈优化，落到三层能力：**Agentic KV**（框架调度）、**Mega Kernel**（设备内流水）、**Kernel Agent**（跨芯片算子自动生成调优）。重点纠正 LRU 对 Agent 暂停会话的误删；给出 Mega Kernel 相对 Kernel-per-Op 的少启动/少搬运/少等待；并用 Master–Sub Agent 并行探索（PyTorch KernelAgent 案例 9.52ms→1.95ms，约 **4.88×**）与 PPU/AMD 迁移实测证明可规模化交付。

### Key points
1. **Dev Loop：** SLA/P99/TTFT → Throughput/RT → Profiler/Trace → 瓶颈归属 → 调用三层能力 → 回归验证；强调证据沉淀与可复现闭环。
2. **三层能力域：** 框架层 **Agentic KV**；计算层 **Mega Kernel**；多芯片平台层 **Kernel Agent**。
3. **Agentic KV 痛点：** Agent 调工具/等人时 KV “变旧”；**停得久 ≠ 价值低**；LRU 误删高价值会话 → 被迫重新 Prefill（高带宽、高延迟、更耗能）。
4. **Agentic KV 调度：** 感知会话生命周期（运行/暂停/恢复/结束）+ KV 自身信号（重建成本、命中次数、占用字节）→ 价值排序 → 调度决策。
5. **三态策略：** 绿·优先保留（活跃即时恢复）；黄·提前准备/备用记忆；红·低价值快速腾挪释放。
6. **传统 Kernel-per-Op：** Host-driven；算子间经 host 与全局内存同步；上游全完成下游才能开。
7. **Mega Kernel：** Device-resident Task Graph；算子拆为 SM tile/task，数据就绪即下游启动并流水；**少启动 / 少搬运 / 少等待**。
8. **名言：** “当执行进入微秒尺度，性能问题不再只存在于 kernel 内，更存在于 kernel 之间。”
9. **Mega Kernel 四层协同：** ①模型计算图（Fusion Boundary）②SM 级任务图（Task Geometry）③设备内运行时（Placement & Pipeline）④架构原生内核（Hardware-Native Kernel）。
10. **工程结果观：** 性能可迁移、效率可预期、速度可转化、交付可验证；提醒“并非越大越好”——动态突发下需平衡单位收益、能耗与稳定。
11. **算子供给难题：** 模型/算子类型 × 输入规模精度 × 硬件平台代际爆炸；AI Agent 组织探索，专家聚焦算法与验收。
12. **Kernel Agent 案例与迁移：** Master–Sub 双层编排 + Knowledge/Tools/Records 经验库；H100 BF16 矩阵向量乘 8 轮并行优化 **4.88×**；PPU 相对 SGLang：RMSNorm+量化约 1.23–1.26×，SiLU 链约 1.23–1.29×，**MoE gate+mask+copy 约 1.56–2.13×**；AMD：DSA Decode **1.6×**、GDN 递推核 **1.18×**；PPU MHC **1.79×**、复杂融合链 **1.56–2.13×**。

### Sections

#### 1. Dev Loop 与三层能力总览
- 以 Profiler/Trace 下钻为枢纽，把优化任务映射到 Agentic KV / Mega Kernel / Kernel Agent。

#### 2. Agentic KV：从 Agent 感知到 KVCache 调度
- 重构价值排序：高价值 ≠ 最近访问。
- SESSION 注入（活跃持有者、存活/共享会话权重）与价值信号融合。
- 运行期保护、提前准备、快速腾挪三段策略。

#### 3. Mega Kernel：从算子接力到设备内流水
- Host-driven → Device-resident。
- 压缩执行空洞、增加有效计算、扩大并行（更多 rollout / 更高精度 / 更实时交互）。
- 四层协同把一次性手工优化沉淀为可复用图/任务/内核/调度资产。

#### 4. Kernel Agent：算子供给与跨平台迁移
- 专家逐项调优 → Agent 并行探索 + 经验回写。
- 小算子融合与数据复用（片上复用中间状态，减少写回与重复启动）。
- NVIDIA 参考实现 → Kernel Agent 按编译器/线程布局/存储层次/原语适配到 AMD、PPU 及其他硬件。
- 演进方向：经验积累、持续适配、子图优化、算法探索；长期目标是可复用算子开发能力，让专家聚焦算法与系统设计。

### Recommended evidence screenshots
| Filename | Caption | Note |
|---|---|---|
| `07-fullstack/t03-18-20.png` | 双讲者标题页 | 资彦义 / 李陈浩文 身份确认 |
| `_intros/t03-19-10.png` / `t03-20-00.png` | Dev Loop + 三层能力 | Agentic KV / Mega Kernel / Kernel Agent |
| `_intros/t03-25-00.png` | Agentic KV：重构 KVCache 价值排序 | “停得久≠价值低”、LRU 误删 |
| `07-fullstack/t03-26-40.png` | Agentic KV：从 Agent 感知到调度 | 绿/黄/红三态 |
| `07-fullstack/t03-30-00.png` | Mega Kernel：算子接力→设备内流水 | 少启动/少搬运/少等待 |
| `07-fullstack/t03-33-20.png` | Mega Kernel 四层协同 | Fusion→SM Task→Runtime→Native Kernel |
| `07-fullstack/t03-36-40.png` | 模型与硬件多样化下的算子供给 | Agent 分工命题 |
| `07-fullstack/t03-40-00.png` | 并行探索与经验回写 | 9.52→1.95ms / 4.88× |
| `07-fullstack/t03-43-20.png` | 小算子融合与数据复用（PPU） | vs SGLang 加速表 |
| `07-fullstack/t03-46-40.png` | 多硬件迁移与平台适配 | AMD/PPU 收益数字 |
| `_bounds/t03-47-30.png` | Kernel Agent 演进方向 | 收束页 |

### Takeaways
- 全栈优化的产品化抓手非常清晰：**Agentic KV（会话价值）+ Mega Kernel（微秒级跨算子流水）+ Kernel Agent（跨芯片自动供给）**。
- Agentic 场景下缓存策略必须从 LRU 升级为**会话生命周期感知的价值排序**，否则 Prefill 成本会吞噬推理 SLA。
- Kernel Agent 用 Master–Sub 并行探索把“专家手艺”沉淀为可迁移经验库，并在 PPU/AMD 上给出可量化加速证据。

---

## Talk 8: 未来大模型推理的软硬件结合系统架构探索

- **Speakers:** 李文韬（舞台桌牌可见「无问芯穹」Infinigence AI；幻灯片品牌含阿里云智能 / 震旦 Insight）
- **Video range:** 约 `03:49:10`（主持人过渡）/ `03:50:00`（开讲）– `04:07:30+`（合作展望收尾）
- **Summary (Chinese):**  
  李文韬从模型规模与硬件不同步增长切入，拆解 Prefill / Decode-Attention / Decode-FFN 的异构资源画像，提出 **P/D 阶段拆分** 与 **AFD（Attention–FFN Disaggregation）层内拆分** 可组合，并据此设计 A 侧大容量高带宽 Attention 卡与 F 侧 LPU FFN 卡（AF Handoff）。仿真侧介绍 **震旦 Insight** 与 **Hisim/HiSim**：无实物端到端+微架构仿真，原生融入 SGLang（保留原生调度逻辑，用虚拟时钟替代真实 GPU Forward），整体仿真准确率 **96%+**；Insight Console 支持 Agent 交互与 Roofline 搜索。最后给出开源与 POC 时间线（Hisim→SGLang/vLLM、AFD PR、P/D-A/F 联合 POC）。

### Key points
1. **议程两块：** ①推理软硬协同优化（模型+硬件 / 架构+硬件 / 下一代硬件）②震旦 Insight 仿真（预测、SGLang 原生融入、模块化精准仿真）。
2. **模型与硬件趋势：** 上下文从 128K 跃升至约 **1M**（如 DeepSeek-V4 Pro）；总参数可达 **2.8T**（Kimi K3）而激活参数约 **95B**（Qwen3.8）——MoE 稀疏激活；硬件容量/带宽/算力**不同步**增长。
3. **单卡对比摘录：** H20/H100/B200/Rubin 算力与 HBM；**Groq 3 LPU** 约 1200 TFLOPS(FP8)、SRAM 带宽约 **250 TB/s**、容量仅约 **0.5GB**——高带宽低容量极端点。
4. **阶段资源画像：** Prefill 偏 Tensor 算力；Decode-Attention 偏 HBM 容量/带宽与反复读 KV；Decode-FFN 偏权重带宽 + Tensor，Scale-out 需求突出。
5. **P/D 拆分：** Prefill 与 Decode 分离，经 KV 传递；可独立配硬件。
6. **AFD：** Attention / Comm / FFN 在 MoE 层内交错；Attention 池（m 实例，KV/序列与 A 权重常驻）↔ FFN/Expert 池（n 实例，专家权重常驻）；每 MoE 层往返一次（dispatch 激活 / combine 输出）。
7. **A/F 卡画像：** A 卡 = 大容量 HBM + 高 KV 访问带宽；F 卡 = 高效矩阵计算 + 高权重访问带宽；batch↑ 且 W 常驻时每专家计算/访存比提高；SRAM 常驻权重使后续 microbatch 无需重载。
8. **下一代硬件提案：** 基于架构分离设计 A 侧 Attention 卡与 F 侧 **LPU FFN 卡**，经 **AF Handoff** 联调。
9. **震旦 Insight：** 无实物仿真（端到端+微架构）；简化完备通道对接 **SGLang / vLLM**；Workload/框架/模型/硬件模块化组合。
10. **Hisim：** 保留 SGLang 原生请求生命周期与调度/组批；不执行真实 GPU Forward，改为耗时预测+虚拟时钟；对接 AIC/Kunlunsim；服务级观察（延迟/吞吐/Prefix cache）；准确率 **整体 96%+**。
11. **Insight Console：** Agent 交互（需求输入与结果解读）→ Roofline 分析与搜索 → 仿真与瓶颈分析；模块化导入硬件/模型/算子/workload。
12. **合作展望时间线：** 9 月 Hisim 合入 SGLang；10 月计划向 SGLang 提供 **AFD PR**；11 月 Hisim 计划合入 vLLM；12 月与 N 家厂商完成 **P/D–A/F** 架构分离联合性能 POC；开源主线 **SGLang × 阿里云**（示例 PR #33824 `tools/sglang-simulator` Merged），栈为 AIConfigurator + KunlunSim → HiSim → 社区反馈。

### Sections

#### 1. 目录与趋势
- 模型上下文与 MoE 参数暴涨 vs 单卡资源非同步增长 → 必须架构级拆分而非单卡堆料。

#### 2. 模型各阶段硬件需求
- 算子机制：多 token 并行写 KV；逐步读历史 KV 做 Attention；读权重批量复用做 FFN。
- 资源条形对比指导 A/F 与 Scale-up/out 配置。

#### 3. 从架构拆分到硬件分离
- P/D 阶段级 + AFD 层内算子级，二者可组合。
- AFD 池化部署与 A/F 专用卡设计、SRAM 权重复用。

#### 4. 震旦 Insight / Hisim 仿真
- 用真实 workload + 主流引擎 + 微架构数据做无实物选型与配比搜索。
- Console 把 Agent、Roofline、仿真串成可操作界面。

#### 5. 开源社区与展望
- Hisim/HiSim 随 SGLang main 演进；扩展接入 AIConfigurator、KunlunSim。
- AFD PR 与多厂商 P/D-A/F POC 作为落地里程碑。

### Recommended evidence screenshots
| Filename | Caption | Note |
|---|---|---|
| `_refine/t03-50-00.png` / `08-future/t03-49-10.png` | 开场/论坛总题过渡 | 李文韬登台；桌牌「无问芯穹」 |
| `08-future/t03-50-50.png` | 目录 | 软硬协同 + Insight 两大块 |
| `_bounds/t03-51-40.png` | 模型与硬件趋势 | 1M 上下文、2.8T / 95B、Groq LPU |
| `08-future/t03-52-30.png` | 模型各阶段硬件需求 | Prefill / Attn / FFN 画像 |
| `08-future/t03-55-00.png` | 从架构拆分到硬件分离 | P/D + AFD 可组合 |
| `08-future/t03-57-30.png` | AFD 架构 | Attention 池 ↔ Expert 池 |
| `08-future/t04-00-00.png` | 下一代 A/F 硬件设计 | A 卡 / LPU F 卡 / AF Handoff |
| `08-future/t04-02-30.png` | 震旦 Insight 仿真系统 | 无实物 + SGLang/vLLM |
| `_refine/t04-03-20.png` | Hisim 仿真细节 | 96%+ 准确率、虚拟时钟 |
| `08-future/t04-05-00.png` | Insight Console | Agent + Roofline + 模块导入 |
| `_refine/t04-06-40.png` | 开源社区 SGLang×阿里云 | PR #33824、HiSim |
| `08-future/t04-07-30.png` | 合作与展望时间线 | 9–12 月里程碑 |

### Takeaways
- 未来推理架构的主轴是 **P/D 与 AFD 双重拆分**，让 KV/Attention 与 Expert/FFN 各自匹配专用硬件（含 LPU）。
- **震旦 Insight / Hisim** 把“下一代硬件尚未到货”的选型与配比问题前移到高仿真（96%+）与开源引擎（SGLang/vLLM）上可验证。
- 落地路径明确：社区合入仿真器 → AFD PR → 多厂商 P/D-A/F POC，与 Talk 6 震旦平台、Talk 7 Kernel Agent 形成“交付—优化—前瞻架构”闭环。

---

## Cross-talk 线索（5–8）

| 主题 | Talk 5 | Talk 6 | Talk 7 | Talk 8 |
|---|---|---|---|---|
| Agentic 记忆/KV | 长期记忆存储需求；KV 分层卸载 | 低延迟超节点收益 | **Agentic KV** 价值调度 | A 侧大容量 KV / AFD |
| 异构硬件 | SCM/PCM/TLC/QLC + EBOF | AL144 超节点、A/F 超节点 | Mega Kernel / 多芯片 | A 卡 + LPU F 卡 |
| 平台品牌 | 磐久、AliSCM、AliFlash | **震旦**交付与诊断 | Kernel Agent | **震旦 Insight / Hisim** |
| 工程闭环 | 软硬分层调度 | 仿真·压测·诊断 | Dev Loop + 经验回写 | Insight Console + 开源 POC |

> 注：用户提及的 UMX、Beluga 等名称未在 Talks 5–8 抽样幻灯中出现，或属论坛更早场次；本笔记仅收录本四场幻灯可见专名与数字。
