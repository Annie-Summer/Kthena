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


def pick_metrics(points: list[dict]) -> list[tuple[str, str, str]]:
    """Build up to 6 metric cards with complete labels/values (no ellipsis)."""
    rows: list[tuple[str, str, str]] = []
    for tp in points:
        if len(rows) >= 6:
            break
        ms = [clean(m) for m in (tp.get("metrics") or []) if clean(m)]
        title = short_title(tp.get("title", "指标"), 12)
        if not ms:
            detail = clean((tp.get("details") or [""])[0])
            if not detail:
                continue
            rows.append((title, "核心口径", take_complete(detail, 28)))
            continue
        for i, m in enumerate(ms):
            if len(rows) >= 6:
                break
            baseline, value = "演讲口径", m
            for sep in ["→", "->", "⇒"]:
                if sep in m:
                    left, right = m.split(sep, 1)
                    left, right = left.strip(), right.strip()
                    if left and right:
                        baseline, value = left, right
                        break
            # Label: prefer short head before colon inside metric, else talk point title
            if "：" in m and len(m.split("：", 1)[0]) <= 12:
                label = m.split("：", 1)[0]
                if baseline == "演讲口径":
                    value = m.split("：", 1)[1].strip() or m
            else:
                label = title if i == 0 else f"{title}·{i+1}"
            rows.append((take_complete(label, 14), take_complete(baseline, 20), take_complete(value, 28)))
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


def insight_field(tp: dict) -> str:
    return clean(tp.get("hcs_insight") or tp.get("competitor_insight") or "")


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

    # Insight: use the primary summary in full (complete viewpoint)
    core = summaries[0] if summaries else overview
    insight = "洞察：" + (core if len(core) <= 100 else take_complete(core, 100))

    # Judgment: 1–2 complete sentences from overview — never mid-cut
    # Only treat 。！？ as hard sentence ends (； often mid-thought)
    ov_sents = split_sentences(overview, seps="。！？")
    if ov_sents:
        judgment_body = ov_sents[0].rstrip("；;")
        if len(judgment_body) < 90 and len(ov_sents) > 1:
            nxt = ov_sents[1].rstrip("；;")
            if len(judgment_body) + len(nxt) <= 180:
                judgment_body = judgment_body + nxt
    else:
        judgment_body = take_complete(overview, 170).rstrip("；;")
    judgment = "一句话判断：" + judgment_body

    cards = []
    for i, tp in enumerate(points[:3], 1):
        details = [clean(d) for d in (tp.get("details") or []) if clean(d)]
        insight_txt = insight_field(tp)
        # Lead = first complete sentence of insight (or first detail) — full clause
        if insight_txt:
            lead_sents = split_sentences(insight_txt)
            lead = lead_sents[0] if lead_sents else insight_txt
            if len(lead) > 70:
                lead = take_complete(lead, 70)
        else:
            lead = take_complete(details[0] if details else tp.get("title", ""), 70)
        lead = lead.rstrip("；;、，, ")
        if lead and lead[-1] not in "。！？":
            # Keep as a complete declarative viewpoint without dangling separators
            pass
        bullet_src = details
        bullets = bulletize(bullet_src, limit=3, max_chars=58)
        cards.append((f"{i:02d}  {short_title(tp.get('title', ''), 18)}", lead, bullets))
    while len(cards) < 3:
        cards.append((f"{len(cards)+1:02d}  补充要点", "详见技术纪要 Word", ["• 展开阅读 docs 对应议题"]))

    metrics = pick_metrics(points)

    # Action: join complete summaries (full sentences)
    action_bits = summaries[:3] if summaries else [insight_field(tp) for tp in points[:2] if insight_field(tp)]
    action_body = "；".join(b.rstrip("。；;") for b in action_bits if b)
    if action_body and not action_body.endswith(("。", "；")):
        action_body += "。"
    action = "可落地动作：" + action_body

    source = f"来源：{source_url} · Talk {tid} {speaker}"
    if audience_note:
        source = f"{source}  ·  视角：{audience_note}"

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
        "audience": "HCS 技术规划",
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
