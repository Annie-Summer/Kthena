#!/usr/bin/env python3
"""为 PAI / Agent Infra 论坛各子议题生成与 CIPU 同风格的一页洞察 PPT（洞察页+截图佐证页）。

文案原则：完整、明确、清晰；禁止用省略号截断观点。过长时按句号/分号取整句，或改写为仍完整的短句。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

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


def textbox(slide, x, y, w, h, text, size=14, bold=False, color=DARK, align=PP_ALIGN.LEFT, anchor=None):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.auto_size = None
        try:
            tf._txBody.bodyPr.set("anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor])
        except Exception:
            pass
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    set_run(run, size=size, bold=bold, color=color)
    return box


def multilines(slide, x, y, w, h, lines, size=13, color=MID, spacing=3, bold_first=False):
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


def clean(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = s.replace("…", "").replace("...", "")
    return s


def split_sentences(s: str, seps: str = "。！？；;") -> list[str]:
    s = clean(s)
    if not s:
        return []
    parts: list[str] = []
    buf = ""
    for ch in s:
        buf += ch
        if ch in seps:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if p]


def take_complete(s: str, max_chars: int) -> str:
    """Keep whole sentence(s) that fit. Never append ellipsis; never cut mid-sentence."""
    s = clean(s)
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    sentences = split_sentences(s)
    acc = ""
    for sent in sentences:
        candidate = (acc + sent).strip()
        if len(candidate) <= max_chars:
            acc = candidate
        else:
            break
    if acc:
        return acc
    # Single overlong sentence: keep a complete clause ending with ，/： if that clause itself is a clear viewpoint
    chunk = s[:max_chars]
    for sep in ["；", ";", "。", "！", "？"]:
        idx = chunk.rfind(sep)
        if idx >= 12:
            return chunk[: idx + 1].strip()
    for sep in ["，", ","]:
        idx = chunk.rfind(sep)
        if idx >= max(20, max_chars * 2 // 3):
            # Only accept long-enough clause so meaning stays intact
            return chunk[:idx].strip()
    # Prefer returning the full original over a mangled fragment
    return s


def short_title(title: str, max_chars: int = 18) -> str:
    title = clean(title)
    # Prefer left of colon for punchy CIPU-style titles
    for sep in ["：", ":", "——", "—", " - "]:
        if sep in title:
            left, right = title.split(sep, 1)
            left, right = left.strip(), right.strip()
            # Prefer right if left is generic/long; else left
            if 4 <= len(right) <= max_chars:
                return right
            if 4 <= len(left) <= max_chars:
                return left
            cand = right if len(right) < len(left) else left
            return take_complete(cand, max_chars)
    return take_complete(title, max_chars)


def bulletize(details: list[str], limit=4, max_chars=72) -> list[str]:
    """Keep complete viewpoints; prefer full sentences over mid-clause cuts."""
    out = []
    for d in details:
        if len(out) >= limit:
            break
        t = clean(d)
        if not t:
            continue
        t = re.sub(r"^[•\-]\s*", "", t)
        if len(t) > max_chars:
            sents = split_sentences(t)
            if sents:
                # Prefer the first full sentence even if a bit over budget
                if len(sents[0]) <= max_chars + 24:
                    t = sents[0].rstrip("。；;")
                elif "；" in t or ";" in t:
                    first = re.split(r"[；;]", t, 1)[0].strip()
                    t = first if len(first) >= 16 else sents[0].rstrip("。；;")
                else:
                    # Keep the full first sentence — clarity over fitting
                    t = sents[0].rstrip("。；;")
            elif "；" in t or ";" in t:
                t = re.split(r"[；;]", t, 1)[0].strip()
        if not t:
            continue
        out.append("• " + t)
    return out


def metric_has_number(m: str) -> bool:
    return bool(re.search(r"[\d]+(?:\.\d+)?\s*[%％×xX倍]|[+\-−]\s*\d|[\d]+/?分钟|[\d]+/?秒|[\d]+万", m))


def parse_metric(m: str, area: str) -> tuple[str, str, str]:
    """Return (label, compare_context, value). Never use 演讲口径."""
    m = clean(m)
    for sep in ["→", "->", "⇒"]:
        if sep in m:
            left, right = [x.strip() for x in m.split(sep, 1)]
            if left and right:
                return (take_complete(area or left, 14), take_complete(left, 20), take_complete(right, 28))
    if "：" in m:
        left, right = [x.strip() for x in m.split("：", 1)]
        if left and right and len(left) <= 14:
            mid = take_complete(area, 20) if area and area != left else "关键能力"
            return (take_complete(left, 14), mid, take_complete(right, 28))
    # Keep ranges intact: 15%~35% / 2~2.4x / +2~10% / 约 -50%
    m_num = re.search(
        r"^(.*?)("
        r"(?:约\s*)?"
        r"[+\-−]?\d+(?:\.\d+)?"
        r"(?:\s*%?\s*[~～\-–]\s*\d+(?:\.\d+)?%?)?"
        r"\s*(?:%|％|×|x|X|倍)?"
        r"(?:/\w+)?"
        r")$",
        m,
    )
    if m_num and m_num.group(1).strip() and m_num.group(2).strip():
        head, num = m_num.group(1).strip(" ：:-"), m_num.group(2).strip()
        # Avoid splitting when head itself ends with dangling ~ 
        if head.endswith("~") or head.endswith("～"):
            return (take_complete(area or "关键指标", 14), "关键能力", take_complete(m, 28))
        return (take_complete(head or area, 14), take_complete(area, 20) if area else "提升幅度", take_complete(num, 28))
    return (take_complete(area or "关键指标", 14), "关键能力", take_complete(m, 28))


def pick_metrics(points: list[dict]) -> list[tuple[str, str, str]]:
    """Pick up to 6 complete metrics; prefer numeric/contrast items; no 演讲口径."""
    scored: list[tuple[int, int, str, str]] = []
    for tp in points:
        area = short_title(tp.get("title", "指标"), 12)
        ms = [clean(m) for m in (tp.get("metrics") or []) if clean(m)]
        if not ms:
            detail = clean((tp.get("details") or [""])[0])
            if detail:
                scored.append((2, len(detail), area, detail))
            continue
        for m in ms:
            rank = 0 if metric_has_number(m) else (1 if any(s in m for s in ["→", "->", "⇒"]) else 2)
            scored.append((rank, len(m), area, m))
    scored.sort(key=lambda x: (x[0], x[1]))
    rows: list[tuple[str, str, str]] = []
    seen = set()
    for _, _, area, m in scored:
        if len(rows) >= 6:
            break
        label, baseline, value = parse_metric(m, area)
        for bad in ("演讲口径", "核心口径", "宣称口径"):
            if baseline == bad:
                baseline = "能力要点"
            if label == bad:
                label = area
            if value == bad:
                value = m
        key = (label, value)
        if key in seen:
            continue
        seen.add(key)
        rows.append((label, baseline, value))
    while len(rows) < 6:
        rows.append(("—", "—", "—"))
    return rows[:6]


def add_insight_slide(prs, eyebrow, insight, judgment, cards, metrics, action, source, metrics_title="关键指标对比与提升"):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)

    # Header: allow 2-line insight
    rect(slide, 0, 0, W, Inches(1.2), fill=WHITE, line=None)
    textbox(slide, Inches(0.35), Inches(0.1), Inches(12.6), Inches(0.26), eyebrow, size=12, color=MUTED)
    textbox(slide, Inches(0.35), Inches(0.38), Inches(12.6), Inches(0.72), insight, size=16, bold=True, color=DARK)

    # Judgment: taller so full sentence wraps visibly
    jy = Inches(1.32)
    rect(slide, Inches(0.3), jy, Inches(12.7), Inches(0.82), fill=WHITE, line=BORDER, line_w=1)
    textbox(slide, Inches(0.45), jy + Inches(0.06), Inches(12.4), Inches(0.7), judgment, size=12, bold=True, color=DARK)

    # Three viewpoint cards
    cy = Inches(2.28)
    ch = Inches(2.48)
    cw = Inches(4.1)
    gap = Inches(0.18)
    for i, (title, lead, bullets) in enumerate(cards[:3]):
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

    # Metrics
    my = Inches(4.98)
    textbox(slide, Inches(0.3), my, Inches(8), Inches(0.26), metrics_title, size=13, bold=True, color=DARK)
    mw = Inches(2.05)
    mh = Inches(1.05)
    mg = Inches(0.1)
    for i, (label, baseline, value) in enumerate(metrics[:6]):
        x = Inches(0.3) + i * (mw + mg)
        y = my + Inches(0.28)
        rect(slide, x, y, mw, mh, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.1), y + Inches(0.06), mw - Inches(0.18), Inches(0.22), label, size=10, color=MUTED)
        textbox(slide, x + Inches(0.1), y + Inches(0.28), mw - Inches(0.18), Inches(0.28), baseline, size=10, color=MID)
        textbox(slide, x + Inches(0.1), y + Inches(0.58), mw - Inches(0.18), Inches(0.4), value, size=12, bold=True, color=ACCENT)

    # Footer action: 2 lines
    fy = Inches(6.42)
    rect(slide, 0, fy, W, H - fy, fill=WHITE, line=None)
    textbox(slide, Inches(0.35), fy + Inches(0.08), Inches(12.6), Inches(0.55), action, size=11, bold=True, color=DARK)
    textbox(slide, Inches(0.35), fy + Inches(0.62), Inches(12.6), Inches(0.28), source, size=9, color=MUTED)
    return slide


def add_evidence_slide(prs, eyebrow, items):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, fill=BG)
    rect(slide, 0, 0, W, Inches(0.95), fill=WHITE, line=None)
    textbox(slide, Inches(0.4), Inches(0.16), Inches(12.5), Inches(0.28), eyebrow, size=12, color=MUTED)
    textbox(slide, Inches(0.4), Inches(0.42), Inches(12.5), Inches(0.4), "数据佐证｜官方回放截图", size=22, bold=True, color=DARK)

    n = max(len(items), 1)
    gap = Inches(0.22)
    margin = Inches(0.35)
    usable = W - 2 * margin - gap * (n - 1)
    cw = usable / n
    ch = Inches(5.55)
    cy = Inches(1.15)

    for i, (img_path, highlight, caption) in enumerate(items[:3]):
        x = margin + i * (cw + gap)
        rect(slide, x, cy, cw, ch, fill=WHITE, line=BORDER, line_w=1)
        textbox(slide, x + Inches(0.12), cy + Inches(0.1), cw - Inches(0.24), Inches(0.42), highlight, size=12, bold=True, color=ACCENT)
        ix = x + Inches(0.12)
        iy = cy + Inches(0.55)
        iw = cw - Inches(0.24)
        ih = Inches(4.1)
        path = Path(img_path)
        if path.exists():
            with Image.open(path) as im:
                aw, ah = im.size
            scale = min(float(iw) / aw, float(ih) / ah)
            dw = int(aw * scale)
            dh = int(ah * scale)
            ox = ix + (iw - dw) / 2
            oy = iy + (ih - dh) / 2
            slide.shapes.add_picture(str(path), int(ox), int(oy), width=dw, height=dh)
        else:
            textbox(slide, ix, iy, iw, Inches(0.4), f"[缺少截图: {path.name}]", size=12, color=ACCENT)
        textbox(slide, x + Inches(0.12), cy + Inches(4.85), cw - Inches(0.24), Inches(0.55), caption, size=11, color=MID)

    textbox(
        slide,
        Inches(0.4),
        Inches(6.95),
        Inches(12.5),
        Inches(0.3),
        "截图裁自云栖大会官方回放幻灯主体，作指标与结论佐证。",
        size=10,
        color=MUTED,
    )
    return slide


def crop_evidence(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 20000:
        return dst
    im = Image.open(src).convert("RGB")
    w, h = im.size
    top = int(h * 0.08)
    bot = int(h * 0.94)
    right = int(w * 0.58)
    crop = im.crop((int(w * 0.01), top, right, bot))
    if crop.width > 1400:
        nh = int(crop.height * 1400 / crop.width)
        crop = crop.resize((1400, nh), Image.Resampling.LANCZOS)
    crop.save(dst, "PNG", optimize=True)
    return dst


def load_talks(notes_dir: Path) -> list[dict]:
    talks = []
    for name in ["talks_1_5.json", "talks_6_10.json", "talks.json"]:
        path = notes_dir / name
        if not path.exists() or path.stat().st_size == 0:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        talks.extend(data["talks"] if isinstance(data, dict) else data)
    seen = set()
    uniq = []
    for t in talks:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        uniq.append(t)
    return sorted(uniq, key=lambda x: x["id"])


def strip_hcs_framing(text: str) -> str:
    """Remove HCS/友商「应该怎么做」口吻，保留可迁移的启示本身。"""
    t = clean(text)
    repls = [
        (r"^HCS\s*技术规划应", ""),
        (r"^HCS\s*规划应", ""),
        (r"^HCS\s*应", ""),
        (r"^对标\s*HCS[^\s，。；]*[，。；]?", ""),
        (r"[，；]?\s*写入\s*HCS[^，。；]*", ""),
        (r"进入\s*HCS\s*产品目录", "纳入产品能力目录"),
        (r"[，；]?\s*作为与公有云[^。]*", ""),
        (r"^友商需", ""),
        (r"^友商应", ""),
        (r"[，；]?\s*友商应[^。；]*", ""),
        (r"[，；]?\s*友商需[^。；]*", ""),
        (r"[，；]?\s*友商(?:建设|可对标|可借鉴|对标)[^。；]*", ""),
        (r"^演讲给出", ""),
        (r"^指出", ""),
        (r"^仅卖算力与控制台不够；\s*", ""),
        (r"[，；]?\s*驱动\s*CCI/CCE[^。]*", ""),
        (r"[，；]?\s*而不是仅发布概念白皮书。?", ""),
    ]
    for pat, rep in repls:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\bHCS\b", "", t)
    t = clean(t).lstrip("，,；;：: ")
    t = re.sub(r"[，,；;]+\s*([。！？])", r"\1", t)
    t = re.sub(r"[，,；;]+$", "", t)
    return clean(t)


def to_revelation(text: str) -> str:
    """Normalize a note into an insight/revelation sentence (no HCS action plan)."""
    t = strip_hcs_framing(text)
    if not t:
        return ""
    t = re.sub(r"^应立项", "宜建设", t)
    t = re.sub(r"^立项", "宜建设", t)
    t = re.sub(r"^应把", "需要把", t)
    t = re.sub(r"^把(?=「|Agent|托管|评测)", "需要把", t)
    t = re.sub(r"^应按", "宜按", t)
    t = re.sub(r"^按(?=Use/In/RL|三类)", "宜按", t)
    t = re.sub(r"^应在", "宜在", t)
    t = re.sub(r"^应同时", "需要同时", t)
    t = re.sub(r"^应提供", "需要提供", t)
    t = re.sub(r"^应默认", "宜默认", t)
    t = re.sub(r"^应看", "应关注", t)
    t = re.sub(r"^将「", "宜把「", t)
    t = clean(t)
    # Repair tails truncated by stripping planning clauses
    if re.search(r"(宜把|需要把|将)「[^」]+」\s*$", t):
        t = t.rstrip("。；; ") + "作为规模与弹性的硬指标"
    if t and t[-1] not in "。！？":
        t += "。"
    return t


def company_of(talk: dict) -> str:
    org = clean(talk.get("org") or "")
    title = clean(talk.get("title") or "")
    blob = org + " " + title
    if "小米" in blob:
        return "小米"
    if "智元" in blob:
        return "智元"
    if "生数" in blob:
        return "生数科技"
    if "小红书" in blob:
        return "小红书"
    if "朗新" in blob:
        return "朗新"
    if "CARIAD" in blob.upper() or "大众" in blob:
        return "CARIAD"
    if "费莫" in blob or "穹彻" in blob or "流形" in blob:
        return "具身智能生态"
    if "阿里" in blob or "阿里云" in org or "PAI" in blob or "ACK" in blob or "百炼" in blob:
        return "阿里云"
    head = org.split("·")[0].split("/")[0].strip()
    return head or "阿里云"


def product_of(talk: dict) -> str:
    title = clean(talk.get("title") or "")
    overview = clean(talk.get("overview") or "")
    org = clean(talk.get("org") or "")
    blob = title + " " + overview + " " + org
    candidates = [
        "Agent Sandbox",
        "Agent Infra",
        "PAI-DLC",
        "PAI-InferX",
        "PAI-TurboX",
        "Physical AI",
        "Agentic AI Platform",
        "Agentic Inference",
        "百炼",
        "ACK",
        "Argo",
        "Ray on ACK",
        "CrystalLLM",
        "PAI-RLS",
        "Vidu",
        "MEGo",
        "PAI",
    ]
    found = []
    for c in candidates:
        if c in blob and c not in found:
            # Avoid adding PAI if a more specific PAI-* already present
            if c == "PAI" and any(x.startswith("PAI") for x in found):
                continue
            found.append(c)
        if len(found) >= 2:
            break
    if found:
        return " / ".join(found[:2])
    t = re.sub(r"^(从.+到|面向|基于)", "", title)
    return short_title(t, 22)


def strip_talk_framing(text: str) -> str:
    t = clean(text)
    patterns = [
        r"^本场系统给出",
        r"^本场围绕",
        r"^本场展示",
        r"^本场为",
        r"^本场前半由[^，。：]+[，：]",
        r"^本场前半由[^：]+：",
        r"^本场后半由[^，。：]+[，：]",
        r"^本场后半由[^：]+：",
        r"^后半由[^，。：]+[，：]",
        r"^前半由[^，。：]+[，：]",
        r"^本演讲系统阐述",
        r"^本演讲",
        r"^演讲围绕",
        r"^演讲主张",
        r"^演讲提出",
        r"^演讲指出",
        r"^演讲从",
        r"^由[^，]{1,12}产品化讲解",
        r"^由[^，]{1,12}拆解",
        r"^由[^，]{1,12}展开",
        r"^圆桌由[^，]+主持[，,]?",
        r"^邀请[^，]+，",
    ]
    for pat in patterns:
        t = re.sub(pat, "", t)
    t = clean(t).lstrip("，,：: ")
    t = re.sub(r"^[^。]{0,30}如何重写", "重写", t)
    t = re.sub(r"^[^。]{0,20}(讲解|拆解|展开)[^：]{0,20}：", "", t)
    # Remove “某人介绍/分享/系统介绍 …” speaker framing anywhere near the start
    t = re.sub(
        r"^[^。；]{0,24}?(?:资深技术专家|高级解决方案架构师|创始人|CEO|科学家)?[^。；]{0,16}?(?:系统)?(?:介绍|分享|讲解|拆解|指出)[^：]{0,40}[：:，,]?",
        "",
        t,
    )
    # “某人分享X如何把A升级为B” → keep B-impact clause if present
    t = re.sub(r"^.*?如何把「[^」]+」升级为「([^」]+)」[。．]?", r"目标是实现「」。", t)
    t = re.sub(r"^.*?如何把(.+?)升级为(.+?)[。．]", r"目标是从升级为。", t)
    # Drop leftover “后半由严龙以…给出”
    t = re.sub(r"[。；]?\s*后半由[^。]+", "", t)
    t = re.sub(r"[。；]?\s*前半由[^。]+", "", t)
    return clean(t).lstrip("，,：: ")


def build_insight_line(summaries: list[str], overview: str, points: list[dict]) -> str:
    # Prefer first usable summary (primary insight), not the shortest tail note
    candidates: list[str] = []
    for s in summaries:
        rev = to_revelation(s)
        if rev and len(rev) >= 16:
            candidates.append(rev)
    if not candidates and points:
        for tp in points[:3]:
            raw = clean(tp.get("competitor_insight") or tp.get("hcs_insight") or "")
            rev = to_revelation(raw)
            if rev:
                candidates.append(rev)
                break
    if not candidates:
        candidates.append(to_revelation(overview) or overview)
    core = candidates[0]
    if len(core) > 100:
        core = take_complete(core, 100)
    return "洞察：" + core


def build_judgment_line(talk: dict) -> str:
    company = company_of(talk)
    product = product_of(talk)
    impact = strip_talk_framing(clean(talk.get("overview") or ""))
    impact = strip_hcs_framing(impact)
    impact = re.sub(r"^.*?的?(形态判断与产品架构|解决方案最佳实践|联合实践)[：:]", "", impact)
    impact = re.sub(r"^.*?与.+的结合[：:]", "", impact)
    # Side labels like “ACK 侧给出 / 生数侧介绍”
    impact = re.sub(r"^[A-Za-z0-9\u4e00-\u9fff ]{1,16}侧\s*(?:给出|介绍|展示)[：,]?", "", impact)
    impact = re.sub(r"[；;]\s*[A-Za-z0-9\u4e00-\u9fff ]{1,16}侧\s*(?:给出|介绍|展示)[：,]?", "；", impact)
    impact = re.sub(r"^指出", "", impact)
    impact = re.sub(r"^提出", "", impact)
    impact = re.sub(r"^演讲给出", "", impact)
    impact = re.sub(r"[。；]\s*演讲给出", "。", impact)
    impact = re.sub(r"。指出", "。", impact)
    # Repair broken quote leftovers from speaker-strip, e.g. “I提效」.”
    impact = re.sub(r"^[^「」]{0,8}」[。．\.]?", "", impact)
    impact = clean(impact).lstrip("，,：:；; ")
    sents = split_sentences(impact, seps="。！？")
    if sents:
        body = sents[0].rstrip("；;")
        if len(body) < 70 and len(sents) > 1 and len(body) + len(sents[1]) <= 150:
            body = body + sents[1].rstrip("；;")
    else:
        body = take_complete(impact, 140).rstrip("；;")
    # Avoid “小米 小米广告…” duplication
    if product and (product.startswith(company) or company in product):
        prefix = product
    elif product:
        prefix = f"{company} {product}"
    else:
        prefix = company
    # De-dup “无尽前延 无尽前延”
    parts = prefix.split()
    dedup = []
    for p in parts:
        if not dedup or p != dedup[-1]:
            dedup.append(p)
    prefix = " ".join(dedup)
    first_prod = product.split("/")[0].strip() if product else ""
    if body.startswith(company) or (first_prod and body.startswith(first_prod)):
        line = body
    else:
        line = f"{prefix}——{body}"
    # Final sweep: no speaker names / 演讲 framing leftovers
    line = re.sub(r"(圆桌由|由)[^，]{1,20}主持[，,]?", "", line)
    line = re.sub(r"[，,]?邀请[^。]+", "", line)
    line = re.sub(r"(?<![A-Za-z])(?:演讲|分享|介绍)(?=从|指出|了|了)", "", line)
    return "一句话判断：" + clean(line)


def card_lead_from_point(tp: dict) -> str:
    """Card lead = revelation from tech point, never HCS action plan."""
    details = [clean(d) for d in (tp.get("details") or []) if clean(d)]
    raw = clean(tp.get("competitor_insight") or tp.get("hcs_insight") or "")
    rev = to_revelation(raw)
    if rev:
        sents = split_sentences(rev, seps="。！？；;")
        lead = sents[0] if sents else rev
        return take_complete(lead.rstrip("；;"), 70)
    if details:
        return take_complete(details[0], 70)
    return short_title(tp.get("title", ""), 40)


def build_from_talk(talk: dict, *, forum_root: Path, source_url: str, audience_note: str = "") -> Path:
    out_dir = forum_root / "docs"
    shots = forum_root / "screenshots"
    evidence_dir = forum_root / "assets" / "evidence" / talk["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    tid = talk["id"]
    title = talk.get("title", "")
    speaker = talk.get("speaker", "")
    org = talk.get("org", "")
    folder = talk["folder"]
    points = talk.get("tech_points") or []
    overview = clean(talk.get("overview") or "")
    summaries = [clean(s) for s in (talk.get("summary_insights") or []) if clean(s)]

    eyebrow = f"{tid} · {speaker}" + (f" · {org}" if org else "")
    eyebrow = take_complete(eyebrow, 90)

    insight = build_insight_line(summaries, overview, points)
    judgment = build_judgment_line(talk)

    cards = []
    for i, tp in enumerate(points[:3], 1):
        details = [clean(d) for d in (tp.get("details") or []) if clean(d)]
        lead = card_lead_from_point(tp).rstrip("；;、，, ")
        bullets = bulletize(details, limit=3, max_chars=58)
        cards.append((f"{i:02d}  {short_title(tp.get('title', ''), 18)}", lead, bullets))
    while len(cards) < 3:
        cards.append((f"{len(cards)+1:02d}  补充要点", "详见技术纪要 Word", ["• 展开阅读 docs 对应议题"]))

    metrics = pick_metrics(points)

    action_bits = []
    for s in summaries[:3]:
        rev = to_revelation(s)
        if rev:
            action_bits.append(rev)
    if not action_bits:
        for tp in points[:3]:
            rev = to_revelation(clean(tp.get("competitor_insight") or tp.get("hcs_insight") or ""))
            if rev:
                action_bits.append(rev)
    action_body = "；".join(b.rstrip("。；;") for b in action_bits if b)
    if action_body and not action_body.endswith(("。", "；")):
        action_body += "。"
    action = "启示要点：" + action_body

    source = f"来源：{source_url} · Talk {tid} {speaker}"

    ev_items = []
    for tp in points:
        if len(ev_items) >= 3:
            break
        img = tp.get("image")
        if not img:
            continue
        src = shots / folder / img
        if not src.exists():
            continue
        dst = evidence_dir / f"{Path(img).stem}-crop.png"
        crop_evidence(src, dst)
        ms = [clean(m) for m in (tp.get("metrics") or []) if clean(m)]
        if ms:
            highlight = take_complete(" · ".join(ms[:2]), 36)
        else:
            highlight = short_title(tp.get("title", ""), 24)
        ev_items.append((dst, highlight, take_complete(tp.get("title", ""), 36)))
    if len(ev_items) < 3:
        folder_pngs = sorted((shots / folder).glob("*.png"))
        for src in folder_pngs:
            if len(ev_items) >= 3:
                break
            if any(src.stem in str(p[0]) for p in ev_items):
                continue
            dst = evidence_dir / f"{src.stem}-crop.png"
            crop_evidence(src, dst)
            ev_items.append((dst, "官方回放截图", take_complete(src.stem, 28)))

    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    add_insight_slide(prs, eyebrow, insight, judgment, cards, metrics, action, source)
    add_evidence_slide(prs, eyebrow, ev_items)

    safe_title = re.sub(r'[\\/:*?"<>|]', "", title)[:28]
    out = out_dir / f"洞察一页-{tid}-{safe_title}.pptx"
    prs.save(out)
    art = Path("/opt/cursor/artifacts/yunqi-insight-ppt")
    art.mkdir(parents=True, exist_ok=True)
    prs.save(art / out.name)
    return out


FORUMS = {
    "pai": {
        "root": Path("/workspace/yunqi-2026-pai-forum"),
        "source": "https://yunqi.aliyun.com/2026/session?agendaId=123",
        "audience": "",
    },
    "agenda201": {
        "root": Path("/workspace/yunqi-2026-agenda-201"),
        "source": "https://yunqi.aliyun.com/2026/session?agendaId=201",
        "audience": "",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forum", choices=["pai", "agenda201", "all"], default="all")
    args = ap.parse_args()
    targets = list(FORUMS.keys()) if args.forum == "all" else [args.forum]
    for key in targets:
        cfg = FORUMS[key]
        talks = load_talks(cfg["root"] / "notes")
        print(f"=== {key}: {len(talks)} talks ===")
        for talk in talks:
            out = build_from_talk(
                talk,
                forum_root=cfg["root"],
                source_url=cfg["source"],
                audience_note=cfg["audience"],
            )
            print("wrote", out)


if __name__ == "__main__":
    main()
