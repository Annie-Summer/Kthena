#!/usr/bin/env python3
"""一页洞察：Agentic Inference 全链路优化（含具体启示）。"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
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


def textbox(slide, x, y, w, h, text, size=14, bold=False, color=DARK):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = text
    set_run(run, size=size, bold=bold, color=color)
    return box


def multilines(slide, x, y, w, h, lines, size=11, color=MID, spacing=2, bold_first=False):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(spacing)
        run = p.add_run()
        run.text = line
        set_run(
            run,
            size=size,
            bold=(bold_first and i == 0),
            color=DARK if (bold_first and i == 0) else color,
        )
    return box


def main():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)
    rect(slide, 0, 0, W, Inches(1.28), fill=WHITE, line=None)

    # Title in requested style
    textbox(
        slide,
        Inches(0.35),
        Inches(0.1),
        Inches(12.6),
        Inches(0.28),
        "05 · 李文鹏 · 阿里云 PAI · Agentic Inference",
        size=11,
        color=MUTED,
    )
    textbox(
        slide,
        Inches(0.35),
        Inches(0.38),
        Inches(12.6),
        Inches(0.78),
        "从「Agentic Inference：推理系统的全链路优化」看阿里云 PAI 围绕有状态推理全链路优化的创新实践",
        size=17,
        bold=True,
        color=DARK,
    )

    # Judgment
    jy = Inches(1.38)
    rect(slide, Inches(0.3), jy, Inches(12.7), Inches(0.7), fill=WHITE, line=BORDER, line_w=1)
    textbox(
        slide,
        Inches(0.45),
        jy + Inches(0.08),
        Inches(12.4),
        Inches(0.56),
        "一句话判断：Agentic 负载把推理从无状态 QPS 问题，改写成「会话连续 + KV 命中 + Token 成本」问题；"
        "PAI 以流量调度 / 引擎执行 / 全局缓存三层协同应对，并用智能选模把质量拉到旗舰水位、成本降约 65%。",
        size=12,
        bold=True,
        color=DARK,
    )

    cards = [
        (
            "01  负载重定义",
            "启示：先按有状态负载建模，再谈引擎调优",
            [
                "• 长上下文：4K Token 请求 KV 可超 200MB",
                "• 前缀重叠决定 TTFT/吞吐，命中率是一等指标",
                "• 流控按 Token 而非 QPS；同会话需实例亲和",
            ],
        ),
        (
            "02  三层协同架构",
            "启示：路由 + PD/并行感知 + 全局 KV 必须一体交付",
            [
                "• 调度：Session/Cache-Aware，亲和优先、均衡兜底",
                "• 引擎：全形态 PD + TP/EP/DP 感知，兼容 vLLM/SGLang",
                "• FlashKV：DRAM+SSD 全局池，缩容/升级不丢缓存",
            ],
        ),
        (
            "03  成本与安全闭环",
            "启示：用选模降本，用可验证安全替代口头承诺",
            [
                "• 智能选模：质量 82.7% 对齐旗舰，成本指数 100→35.1",
                "• 联邦调度：主区域全局决策，库存跨 Region 随取随用",
                "• PAI-CC：TEE + 远程证明，模型/Prompt 可验证密态执行",
            ],
        ),
    ]
    cy, ch, cw, gap = Inches(2.22), Inches(2.55), Inches(4.1), Inches(0.18)
    for i, (title, lead, bullets) in enumerate(cards):
        x = Inches(0.3) + i * (cw + gap)
        rect(slide, x, cy, cw, ch, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.14), cy + Inches(0.1), cw - Inches(0.28), Inches(0.32), title, size=14, bold=True, color=ACCENT)
        multilines(
            slide,
            x + Inches(0.14),
            cy + Inches(0.44),
            cw - Inches(0.28),
            ch - Inches(0.55),
            [lead] + bullets,
            size=11,
            color=MID,
            spacing=2,
            bold_first=True,
        )

    metrics = [
        ("Cache 命中率", "基线 → Cache-Aware", "38.65%→78.62%"),
        ("TTFT", "Cache-Aware 调度", "-33.3%"),
        ("TPS", "Cache-Aware 调度", "+100%"),
        ("FlashKV 命中率", "再叠加全局 KV", "78.62%→94.32%"),
        ("FlashKV TTFT/TPS", "相对前一阶段", "-25% / +40%"),
        ("智能选模成本", "纯 L3 → Auto", "-65%"),
    ]
    my = Inches(4.92)
    textbox(slide, Inches(0.3), my, Inches(10), Inches(0.26), "关键指标对比与提升", size=13, bold=True, color=DARK)
    mw, mh, mg = Inches(2.05), Inches(1.0), Inches(0.1)
    for i, (label, baseline, value) in enumerate(metrics):
        x = Inches(0.3) + i * (mw + mg)
        y = my + Inches(0.28)
        rect(slide, x, y, mw, mh, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.08), y + Inches(0.05), mw - Inches(0.14), Inches(0.22), label, size=10, color=MUTED)
        textbox(slide, x + Inches(0.08), y + Inches(0.28), mw - Inches(0.14), Inches(0.28), baseline, size=9, color=MID)
        textbox(slide, x + Inches(0.08), y + Inches(0.55), mw - Inches(0.14), Inches(0.38), value, size=12, bold=True, color=ACCENT)

    fy = Inches(6.38)
    rect(slide, 0, fy, W, H - fy, fill=WHITE, line=None)
    textbox(
        slide,
        Inches(0.35),
        fy + Inches(0.06),
        Inches(12.6),
        Inches(0.55),
        "具体启示：把会话亲和与 KV 命中率写入调度 SLO；用三层 Serving 架构替代单点引擎调优；"
        "以智能选模做质量-成本帕累托；用全局 KV 与模型分发吃掉弹性税；用 TEE 远程证明把安全从承诺升级为可验证。",
        size=11,
        bold=True,
        color=DARK,
    )
    textbox(
        slide,
        Inches(0.35),
        fy + Inches(0.6),
        Inches(12.6),
        Inches(0.28),
        "来源：云栖大会｜阿里云 PAI《Agentic Inference：推理系统的全链路优化》",
        size=9,
        color=MUTED,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    out = OUT / "洞察一页-05-Agentic Inference：从议题看有状态推理全链路优化.pptx"
    # Also refresh the canonical talk-05 filename used earlier
    out2 = OUT / "洞察一页-05-Agentic Inference：推理系统的全链路优化.pptx"
    prs.save(out)
    prs.save(out2)
    prs.save(ART / out2.name)
    print("wrote", out)
    print("wrote", out2)


if __name__ == "__main__":
    main()
