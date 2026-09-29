#!/usr/bin/env python3
"""Generate Word summaries for Yunqi 2026 CIPU forum talks."""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path("/workspace/yunqi-2026-cipu-forum")
NOTES = ROOT / "notes"
DOCS = ROOT / "docs"
SHOTS = ROOT / "screenshots"


def set_run_font(run, name="微软雅黑", size=11, bold=False, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        set_run_font(run, size=16 if level == 1 else 13, bold=True)
    return p


def add_para(doc, text, *, bold=False, size=11, space_after=6):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.25
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item)
        set_run_font(run, size=11)
        p.paragraph_format.space_after = Pt(3)


def add_image(doc, path: Path, caption: str | None = None, width=5.8):
    if not path.exists():
        add_para(doc, f"[缺少截图: {path.name}]", bold=True)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    if caption:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = cp.add_run(caption)
        set_run_font(r, size=9, color=(90, 90, 90))


def add_evidence_images(doc, shot_dir: str, images: list[dict]):
    """Place evidence screenshots immediately under the related content."""
    for img in images:
        path = SHOTS / shot_dir / img["file"]
        add_image(doc, path, caption=img.get("caption"))
        if img.get("note"):
            add_para(doc, f"佐证说明：{img['note']}", size=10, space_after=10)


def build_doc(meta: dict) -> Path:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)

    add_heading(doc, meta["title"], 1)
    add_para(doc, f"演讲嘉宾：{meta['speakers']}", bold=True)
    add_para(doc, f"大会议程时间：{meta['agenda_time']}")
    add_para(doc, f"视频时间轴：{meta['video_time']}")
    add_para(doc, f"来源：2026云栖大会 · Agentic AI 时代的算力与存储服务器革新")
    add_para(doc, f"回放链接：https://yunqi.aliyun.com/2026/session?agendaId=164")

    add_heading(doc, "一、内容摘要", 2)
    add_para(doc, meta["summary"])

    add_heading(doc, "二、核心要点", 2)
    add_bullets(doc, meta["key_points"])

    add_heading(doc, "三、分节梳理与PPT佐证", 2)
    add_para(
        doc,
        "以下按议题结构展开；每节文字要点之后立即附上对应 PPT 截图作为佐证。",
        size=10,
    )
    for block in meta.get("blocks", []):
        add_para(doc, block["heading"], bold=True, size=12, space_after=4)
        add_bullets(doc, block.get("bullets", []))
        add_evidence_images(doc, meta["shot_dir"], block.get("images", []))

    if meta.get("takeaways"):
        add_heading(doc, "四、结论与启示", 2)
        add_bullets(doc, meta["takeaways"])

    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / meta["filename"]
    doc.save(out)
    return out


def main():
    notes_path = NOTES / "talk_notes.json"
    data = json.loads(notes_path.read_text(encoding="utf-8"))
    outputs = []
    for meta in data:
        path = build_doc(meta)
        outputs.append(str(path))
        print("wrote", path)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
