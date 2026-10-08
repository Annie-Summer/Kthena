#!/usr/bin/env python3
"""手写「洞察一页-08 容器服务×小红书」：Cost/Token 主线，优先两页洞察 + 佐证页。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
SHOTS = ROOT / "screenshots" / "08-che-xiong-rednote"
EVIDENCE = ROOT / "assets" / "evidence" / "08"
ART = Path("/opt/cursor/artifacts/yunqi-insight-ppt")

BG = RGBColor(0xF5, 0xF7, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1A, 0x1A, 0x1A)
MID = RGBColor(0x4A, 0x4A, 0x4A)
MUTED = RGBColor(0x6B, 0x6B, 0x6B)
BORDER = RGBColor(0xD0, 0xD8, 0xDE)
ACCENT = RGBColor(0x8B, 0x1A, 0x2B)
FONT = "Microsoft YaHei"
W = Inches(13.333)
H = Inches(7.5)


def set_run(run, size, bold=False, color=DARK):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = parse_xml(
            f'<a:ea xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" typeface="{FONT}"/>'
        )
        rPr.append(ea)
    else:
        ea.set("typeface", FONT)


def rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    return sh


def textbox(slide, x, y, w, h, text, size=14, bold=False, color=DARK, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    set_run(run, size=size, bold=bold, color=color)
    return box


def multilines(slide, x, y, w, h, lines, size=12, color=MID, spacing=3, bold_first=False):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(spacing)
        run = p.add_run()
        run.text = line
        set_run(run, size=size, bold=(bold_first and i == 0), color=DARK if (bold_first and i == 0) else color)
    return box


def crop_evidence(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    crop = im.crop((int(w * 0.01), int(h * 0.08), int(w * 0.58), int(h * 0.94)))
    if crop.width > 1400:
        nh = int(crop.height * 1400 / crop.width)
        crop = crop.resize((1400, nh), Image.Resampling.LANCZOS)
    crop.save(dst, "PNG", optimize=True)
    return dst


def add_page1(prs):
    """Cost/Token 北极星 + Serving Stack 三件套 + 关键指标。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)
    rect(slide, 0, 0, W, Inches(1.18), fill=WHITE, line=None)

    textbox(slide, Inches(0.35), Inches(0.1), Inches(12.6), Inches(0.26),
            "08 · 车漾 / 熊峰 · 阿里云容器服务 ACK × 小红书", size=12, color=MUTED)
    textbox(slide, Inches(0.35), Inches(0.38), Inches(12.6), Inches(0.7),
            "洞察：以 Cost/Token 为北极星——降 GPU 单价、抬单卡吞吐、抬利用率三杠杆并用；"
            "ACK AI Serving Stack（网关 + InferenceKit + ModelScale）直接打在分母上",
            size=16, bold=True, color=DARK)

    jy = Inches(1.3)
    rect(slide, Inches(0.3), jy, Inches(12.7), Inches(0.78), fill=WHITE, line=BORDER, line_w=1)
    textbox(slide, Inches(0.45), jy + Inches(0.08), Inches(12.4), Inches(0.64),
            "一句话判断：阿里云 ACK × 小红书——Cost/Million Tokens = GPU 小时成本 ÷ (Throughput × Utilization)；"
            "NVIDIA 亦将 Cost per token 定义为推理 TCO 指标。网关智能路由（TTFT -75%、ITL -40%、吞吐 3×）"
            "+ ModelScale 权重秒级加载 + InferenceKit 注入式拓扑优化，把单卡效率做成可复制平台能力。",
            size=12, bold=True, color=DARK)

    cards = [
        (
            "01  Cost/Token 三杠杆",
            "公式：GPU Cost/Hour ÷ (Throughput × Utilization)",
            [
                "• 分子：GPU 选型、潮汐混部、Spot 降单位成本",
                "• 分母吞吐：PD 分离、EP/DP、KVCache Offload/Reuse",
                "• 分母利用率：弹性伸缩、KV 感知路由、数据缓存",
            ],
        ),
        (
            "02  Serving Stack 三件套",
            "每层能力都直接作用于降本",
            [
                "• ModelScale：RDMA+GDR 分层权重，P2P 随规模扩展",
                "• InferenceKit：Webhook→Wrapper→插件，无静默自证",
                "• 推理网关：公平调度 + 负载感知 + 缓存亲和路由",
            ],
        ),
        (
            "03  关键实测收益",
            "从加载、路由到场景吞吐全面兑现",
            [
                "• 模型加载 120s → 20s（ModelScale + Mooncake）",
                "• Agent Coding 2.69× / RAG 1.44× / 写作 1.80×",
                "• Qwen3-32B P2P 加载相对 OSS 提速约 13.5×",
            ],
        ),
    ]
    cy, ch, cw, gap = Inches(2.22), Inches(2.55), Inches(4.1), Inches(0.18)
    for i, (title, lead, bullets) in enumerate(cards):
        x = Inches(0.3) + i * (cw + gap)
        rect(slide, x, cy, cw, ch, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.14), cy + Inches(0.1), cw - Inches(0.28), Inches(0.32),
                title, size=14, bold=True, color=ACCENT)
        multilines(slide, x + Inches(0.14), cy + Inches(0.44), cw - Inches(0.28), ch - Inches(0.55),
                   [lead] + bullets, size=11, color=MID, spacing=2, bold_first=True)

    metrics = [
        ("网关 TTFT", "典型测试场景", "-75%"),
        ("网关 ITL", "典型测试场景", "-40%"),
        ("网关吞吐", "典型测试场景", "3×"),
        ("权重加载", "120s → 20s", "约 6×"),
        ("P2P vs OSS", "Qwen3-32B 65GB", "13.5×"),
        ("跨 NUMA 代价", "吞吐劣化", "-13.4%"),
    ]
    my = Inches(4.92)
    textbox(slide, Inches(0.3), my, Inches(10), Inches(0.26), "关键指标对比与提升", size=13, bold=True, color=DARK)
    mw, mh, mg = Inches(2.05), Inches(1.0), Inches(0.1)
    for i, (label, baseline, value) in enumerate(metrics):
        x = Inches(0.3) + i * (mw + mg)
        y = my + Inches(0.28)
        rect(slide, x, y, mw, mh, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.1), y + Inches(0.06), mw - Inches(0.18), Inches(0.22), label, size=10, color=MUTED)
        textbox(slide, x + Inches(0.1), y + Inches(0.28), mw - Inches(0.18), Inches(0.28), baseline, size=10, color=MID)
        textbox(slide, x + Inches(0.1), y + Inches(0.56), mw - Inches(0.18), Inches(0.36), value, size=14, bold=True, color=ACCENT)

    fy = Inches(6.4)
    rect(slide, 0, fy, W, H - fy, fill=WHITE, line=None)
    textbox(slide, Inches(0.35), fy + Inches(0.08), Inches(12.6), Inches(0.5),
            "启示要点：先立 Cost/Token 公式再选型；Serving Stack 优先打通「权重秒级加载 + 拓扑无静默注入 + KV 感知路由」；"
            "NUMA/ICN64 等拓扑错误会静默吃掉吞吐，必须 Summary 自证生效。",
            size=11, bold=True, color=DARK)
    textbox(slide, Inches(0.35), fy + Inches(0.58), Inches(12.6), Inches(0.28),
            "来源：https://yunqi.aliyun.com/2026/session?agendaId=201 · Talk 08 车漾 / 熊峰 · 第 1/2 页",
            size=9, color=MUTED)


def add_page2(prs):
    """小红书编排演进：静态 PD → 动态 RBG + 生产成果 + RL。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)
    rect(slide, 0, 0, W, Inches(1.1), fill=WHITE, line=None)

    textbox(slide, Inches(0.35), Inches(0.1), Inches(12.6), Inches(0.26),
            "08 · 续 · 小红书推理编排演进与生产成果", size=12, color=MUTED)
    textbox(slide, Inches(0.35), Inches(0.38), Inches(12.6), Inches(0.6),
            "洞察：性能驱动架构持续演进——从单 Pod 到静态 PD（GroupSet），再到动态 PD（RBG 角色化）；"
            "编排、调度与拓扑感知必须同步升级",
            size=16, bold=True, color=DARK)

    jy = Inches(1.2)
    rect(slide, Inches(0.3), jy, Inches(12.7), Inches(0.62), fill=WHITE, line=BORDER, line_w=1)
    textbox(slide, Inches(0.45), jy + Inches(0.08), Inches(12.4), Inches(0.48),
            "一句话判断：小红书 × 阿里云 ACK——同 SLO 下吞吐提升 2~3×、GPU 资源节省约 50%；"
            "生产能力沉淀为开源 RoleBasedGroup（github.com/sgl-project/rbg），适配 vLLM / SGLang。",
            size=12, bold=True, color=DARK)

    cards = [
        (
            "01  静态 PD：GroupSet",
            "组内配比固定，弹性靠组副本数",
            [
                "• PodGroup 固定 P:D（如 2P:1D），Gang 成组调度",
                "• 原地升级 + 四级缓存：镜像/权重/Kernel/KV",
                "• 升级耗时从数十分钟 → 数分钟；分批暂停与容量底线防护",
            ],
        ),
        (
            "02  动态 PD：RBG",
            "Role 为一等编排单元，策略表达协同",
            [
                "• Router/Prefill/Decode/KV 各自扩缩与发布",
                "• 双层 Gang + CoordinatedPolicy（maxSkew）",
                "• KVCache-Aware 全局选路：命中率 + 负载健康",
            ],
        ),
        (
            "03  RL 与工具链延伸",
            "状态复用贯通训练与评测",
            [
                "• 快照四要素：rootfs / 存储 / 内存 / 轨迹 WAL",
                "• Rollout 托管：Env 接入 + Agent Harness 管线",
                "• arena llm：配比生成 / 自动寻优 / 一键部署",
            ],
        ),
    ]
    cy, ch, cw, gap = Inches(1.98), Inches(2.7), Inches(4.1), Inches(0.18)
    for i, (title, lead, bullets) in enumerate(cards):
        x = Inches(0.3) + i * (cw + gap)
        rect(slide, x, cy, cw, ch, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.14), cy + Inches(0.1), cw - Inches(0.28), Inches(0.32),
                title, size=14, bold=True, color=ACCENT)
        multilines(slide, x + Inches(0.14), cy + Inches(0.44), cw - Inches(0.28), ch - Inches(0.55),
                   [lead] + bullets, size=11, color=MID, spacing=3, bold_first=True)

    metrics = [
        ("同 SLO 吞吐", "生产验证", "2~3×"),
        ("GPU 资源", "生产验证", "节省 50%"),
        ("FlashGPU 驻留", "权重切换", "0.6–1.5s"),
        ("ICN64 vs RDMA", "吞吐提升", "+40%~55%"),
        ("ICN64 TTFT", "长输入更明显", "-28%~-35%"),
        ("开源 RBG", "小红书×ACK", "sgl-project/rbg"),
    ]
    my = Inches(4.85)
    textbox(slide, Inches(0.3), my, Inches(10), Inches(0.26), "生产成果与关键能力指标", size=13, bold=True, color=DARK)
    mw, mh, mg = Inches(2.05), Inches(1.0), Inches(0.1)
    for i, (label, baseline, value) in enumerate(metrics):
        x = Inches(0.3) + i * (mw + mg)
        y = my + Inches(0.28)
        rect(slide, x, y, mw, mh, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.1), y + Inches(0.06), mw - Inches(0.18), Inches(0.22), label, size=10, color=MUTED)
        textbox(slide, x + Inches(0.1), y + Inches(0.28), mw - Inches(0.18), Inches(0.28), baseline, size=10, color=MID)
        textbox(slide, x + Inches(0.1), y + Inches(0.56), mw - Inches(0.18), Inches(0.36), value, size=13, bold=True, color=ACCENT)

    fy = Inches(6.35)
    rect(slide, 0, fy, W, H - fy, fill=WHITE, line=None)
    textbox(slide, Inches(0.35), fy + Inches(0.08), Inches(12.6), Inches(0.52),
            "启示要点：静态 PD 先把「成组调度 + 原地升级 + 容量防护」跑稳；动态 PD 再把 Role 拆开，用策略协同替代固定配比；"
            "最终把快照复用与 Rollout 托管接到训推一体，并用开源 RBG 回馈社区。",
            size=11, bold=True, color=DARK)
    textbox(slide, Inches(0.35), fy + Inches(0.58), Inches(12.6), Inches(0.28),
            "来源：https://yunqi.aliyun.com/2026/session?agendaId=201 · Talk 08 车漾 / 熊峰 · 第 2/2 页",
            size=9, color=MUTED)


def add_evidence(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)
    rect(slide, 0, 0, W, Inches(0.95), fill=WHITE, line=None)
    textbox(slide, Inches(0.4), Inches(0.16), Inches(12.5), Inches(0.28),
            "08 · 车漾 / 熊峰 · 阿里云容器服务 ACK × 小红书", size=12, color=MUTED)
    textbox(slide, Inches(0.4), Inches(0.42), Inches(12.5), Inches(0.4),
            "数据佐证｜官方回放截图", size=22, bold=True, color=DARK)

    items = [
        ("t02-52-00.png", "Cost/Token 公式与三杠杆", "Cost per Token 北极星"),
        ("t02-54-00.png", "ACK AI Serving Stack 分层", "网关 / InferenceKit / 存储"),
        ("t03-07-00.png", "静态 PD → 动态 RBG 演进", "小红书编排两阶段"),
    ]
    gap, margin = Inches(0.22), Inches(0.35)
    n = len(items)
    usable = W - 2 * margin - gap * (n - 1)
    cw = usable / n
    cy, ch = Inches(1.15), Inches(5.55)

    for i, (name, highlight, caption) in enumerate(items):
        src = SHOTS / name
        dst = EVIDENCE / f"{Path(name).stem}-crop.png"
        if src.exists():
            crop_evidence(src, dst)
        x = margin + i * (cw + gap)
        rect(slide, x, cy, cw, ch, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.12), cy + Inches(0.1), cw - Inches(0.24), Inches(0.4),
                highlight, size=12, bold=True, color=ACCENT)
        ix, iy = x + Inches(0.12), cy + Inches(0.55)
        iw, ih = cw - Inches(0.24), Inches(4.1)
        if dst.exists():
            with Image.open(dst) as im:
                aw, ah = im.size
            scale = min(float(iw) / aw, float(ih) / ah)
            dw, dh = int(aw * scale), int(ah * scale)
            ox = ix + (iw - dw) / 2
            oy = iy + (ih - dh) / 2
            slide.shapes.add_picture(str(dst), int(ox), int(oy), width=dw, height=dh)
        textbox(slide, x + Inches(0.12), cy + Inches(4.85), cw - Inches(0.24), Inches(0.55),
                caption, size=11, color=MID)

    textbox(slide, Inches(0.4), Inches(6.95), Inches(12.5), Inches(0.3),
            "截图裁自云栖大会官方回放幻灯主体，作指标与结论佐证。", size=10, color=MUTED)


def main():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    add_page1(prs)
    add_page2(prs)
    add_evidence(prs)

    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    out = OUT / "洞察一页-08-容器服务 × 小红书：大模型推理与 Agent RL.pptx"
    prs.save(out)
    prs.save(ART / out.name)
    print("wrote", out)


if __name__ == "__main__":
    main()
