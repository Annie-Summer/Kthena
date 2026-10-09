# 2026云栖大会 · 构建 Agent Infra（agendaId=201）

来源回放：https://yunqi.aliyun.com/2026/session?agendaId=201

场馆：国博一期-4F-大会议室B · 主题：Agentic Cloud、算力与 AI 基础设施

## 文档定位

每个议题一份 Word：偏**技术细节** + **对 HCS 技术规划团队的启示**；每个技术点下附官方回放截图佐证。

## 论坛议程（10 场）

| 编号 | 议题 | 演讲人 |
|------|------|--------|
| 01 | 企业级大规模 Agent Infra 解决方案最佳实践 | 杨旭 |
| 02 | Agent Sandbox 加速训练与评测闭环与百炼 Agent RL/Eval | 洪晓龙 / 罗自荣 |
| 03 | 驾驭百万级 Agent：Sandbox 核心能力与千问办公实践 | 卢萌凯 / 严龙 |
| 04 | 以 ACK 为底座的开放产线与数据飞轮 | 华相 |
| 05 | 敏捷基础设施助力具身智能（智元） | 赵堃 / 尹欣 |
| 06 | 容器智算底座助力生数科技多模态 AI | 张凯 / 姚峥 |
| 07 | 时空智能 Infra：感-算-决一体化 | 沈健 |
| 08 | 容器服务 × 小红书：大模型推理与 Agent RL | 车漾 / 熊峰 |
| 09 | 容器服务 Agent 服务全场景最佳实践 | 胡光 |
| 10 | 朗新：基于 Agent Sandbox 的云端 Agent 平台 | 张栋 |

## 生成

- `screenshots/`：按议题分目录截图
- `notes/`：时间轴与结构化底稿
- `generate_docs.py`：生成 `docs/*.docx`
- `generate_insight_ppt.py`：按子议题生成一页洞察 PPT（洞察页 + 截图佐证页，风格同 CIPU）
  - 洞察写「获得什么启示」，不写内部规划动作；一句话判断只保留公司/产品与影响
  - `python3 generate_insight_ppt.py --forum agenda201`
  - 产出：`docs/洞察一页-XX-*.pptx`，裁图：`assets/evidence/`
- `generate_insight_ppt_08_rednote.py`：Talk 08（ACK × 小红书）手写版——Cost/Token 主线，2 页洞察 + 佐证页
