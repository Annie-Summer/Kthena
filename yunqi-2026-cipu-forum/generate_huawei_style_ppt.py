#!/usr/bin/env python3
"""按华为红风格规范生成三场议题洞察演示文稿。"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent
COVERS = ROOT / "assets" / "covers"
OUT = ROOT / "docs"
ART = Path("/opt/cursor/artifacts/yunqi-docs")

RED = RGBColor(0xCF, 0x0A, 0x2C)
DARK = RGBColor(0x33, 0x33, 0x33)
MID = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0x99, 0x99, 0x99)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xFF, 0xFF, 0xFF)
MOD = RGBColor(0xF5, 0xF5, 0xF5)
MOD_PINK = RGBColor(0xFF, 0xF5, 0xF5)
LINE = RGBColor(0xE5, 0xE5, 0xE5)
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


def rect(slide, x, y, w, h, fill, line=None, line_w=1):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    return sh


def textbox(slide, x, y, w, h, text, size=16, bold=False, color=DARK, align=PP_ALIGN.LEFT, anchor="t"):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    try:
        tf._txBody.bodyPr.set("anchor", {"t": "t", "ctr": "ctr", "b": "b"}[anchor])
    except Exception:
        pass
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    set_run(run, size=size, bold=bold, color=color)
    return box


def multilines(slide, x, y, w, h, lines, size=16, color=MID, spacing=8, bold_flags=None):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(spacing)
        run = p.add_run()
        run.text = line
        bold = bool(bold_flags and bold_flags[i]) if bold_flags else False
        set_run(run, size=size, bold=bold, color=color if not bold else DARK)
    return box


def title_pair(slide, x, y, prefix, suffix, max_w=Inches(12)):
    """前缀24红粗 + 后缀18深灰粗，总字数控制在调用侧。"""
    # draw as one textbox with two runs
    box = slide.shapes.add_textbox(x, y, max_w, Inches(0.55))
    tf = box.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    r1 = p.add_run()
    r1.text = prefix
    set_run(r1, size=24, bold=True, color=RED)
    r2 = p.add_run()
    r2.text = suffix
    set_run(r2, size=18, bold=True, color=DARK)
    return box


def red_top_card(slide, x, y, w, h, fill=MOD):
    """卡片：顶部2-4px红线 + 模块底。"""
    rect(slide, x, y, w, h, fill, line=LINE)
    rect(slide, x, y, w, Pt(3), RED)
    return None


def icon_circle(slide, x, y, r=Inches(0.28)):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, r, r)
    sh.fill.background()
    sh.line.color.rgb = RED
    sh.line.width = Pt(1.5)
    # inner red bar as simple linear icon
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        x + r * 0.28,
        y + r * 0.42,
        r * 0.44,
        Pt(2.5),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = RED
    bar.line.fill.background()
    return sh


def page_chrome(slide, page_no, total, section=""):
    """页脚来源与页码。"""
    textbox(
        slide,
        Inches(0.4),
        Inches(7.15),
        Inches(9),
        Inches(0.25),
        "来源：二零二六云栖大会 · 智能体算力与存储论坛回放整理",
        size=10,
        color=LIGHT,
    )
    textbox(
        slide,
        Inches(10.5),
        Inches(7.15),
        Inches(2.4),
        Inches(0.25),
        f"{page_no} / {total}",
        size=10,
        color=LIGHT,
        align=PP_ALIGN.RIGHT,
    )
    if section:
        textbox(slide, Inches(0.4), Inches(0.18), Inches(8), Inches(0.25), section, size=11, color=LIGHT)


def new_prs():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    return prs


def add_blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def cover_page(prs, cover_path: Path, prefix, suffix, subtitle, meta):
    slide = add_blank(prs)
    # full-bleed image
    slide.shapes.add_picture(str(cover_path), 0, 0, width=W, height=H)
    # dark overlay panel for readability
    rect(slide, 0, Inches(3.8), W, Inches(3.7), DARK)
    # red accent stripe
    rect(slide, 0, Inches(3.8), W, Pt(4), RED)
    # titles on dark panel
    box = slide.shapes.add_textbox(Inches(0.6), Inches(4.1), Inches(12), Inches(0.7))
    tf = box.text_frame
    p = tf.paragraphs[0]
    r1 = p.add_run()
    r1.text = prefix
    set_run(r1, size=28, bold=True, color=RED)
    r2 = p.add_run()
    r2.text = suffix
    set_run(r2, size=22, bold=True, color=WHITE)
    textbox(slide, Inches(0.6), Inches(4.9), Inches(12), Inches(0.45), subtitle, size=16, color=RGBColor(0xCC, 0xCC, 0xCC))
    textbox(slide, Inches(0.6), Inches(5.5), Inches(12), Inches(0.4), meta, size=14, color=LIGHT)
    textbox(slide, Inches(0.6), Inches(6.3), Inches(12), Inches(0.3), "洞察演示文稿", size=12, color=LIGHT)
    return slide


def agenda_page(prs, items, total):
    slide = add_blank(prs)
    rect(slide, 0, 0, W, H, BG)
    title_pair(slide, Inches(0.5), Inches(0.35), "目录", "｜本场结构")
    # 4 agenda cards in 2x2 or vertical list with numbers
    for i, (num, title, desc) in enumerate(items):
        y = Inches(1.2) + i * Inches(1.15)
        red_top_card(slide, Inches(0.5), y, Inches(12.3), Inches(1.0), MOD if i % 2 == 0 else MOD_PINK)
        # big number
        textbox(slide, Inches(0.7), y + Inches(0.22), Inches(1.2), Inches(0.6), num, size=36, bold=True, color=RED)
        textbox(slide, Inches(2.0), y + Inches(0.18), Inches(10), Inches(0.35), title, size=18, bold=True, color=DARK)
        textbox(slide, Inches(2.0), y + Inches(0.55), Inches(10), Inches(0.3), desc, size=14, color=MID)
    page_chrome(slide, 2, total, "目录")
    return slide


def thank_you_page(prs, total):
    slide = add_blank(prs)
    rect(slide, 0, 0, W, H, DARK)
    rect(slide, 0, Inches(3.2), W, Pt(4), RED)
    textbox(slide, Inches(0.5), Inches(2.4), Inches(12.3), Inches(0.7), "感谢聆听", size=48, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    textbox(
        slide,
        Inches(0.5),
        Inches(3.5),
        Inches(12.3),
        Inches(0.5),
        "欢迎交流讨论 · 基于二零二六云栖大会回放整理",
        size=16,
        color=LIGHT,
        align=PP_ALIGN.CENTER,
    )
    textbox(slide, Inches(0.5), Inches(6.8), Inches(12.3), Inches(0.3), f"{total} / {total}", size=10, color=LIGHT, align=PP_ALIGN.CENTER)
    return slide


def build_04():
    prs = new_prs()
    total = 7
    cover_page(
        prs,
        COVERS / "cover-04-kvcache.png",
        "键值缓存",
        "基建化跃迁",
        "从显存开销到可调度、可计量、可分层的推理基础设施",
        "演讲：王正恒 / 徐国强 · 阿里云智能集团",
    )
    agenda_page(
        prs,
        [
            ("01", "核心判断", "键值缓存成为推理资产，而非显存边角料"),
            ("02", "三跃迁路径", "前缀复用 · 多轮持久 · 跨实例池化"),
            ("03", "分层与指标", "一级到四级介质栈与关键提升数字"),
            ("04", "行动建议", "服务等级目标、选型仿真与纵向协同"),
        ],
        total,
    )

    # p3 核心判断
    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "判断", "｜资产化而非技巧化")
    red_top_card(s, Inches(0.5), Inches(1.1), Inches(8.0), Inches(5.5), MOD)
    multilines(
        s,
        Inches(0.75),
        Inches(1.4),
        Inches(7.5),
        Inches(5.0),
        [
            "一句话结论",
            "把键值缓存当作可调度资产：控制面管放置与生命周期，数据面做分层池化。",
            "",
            "关键判断",
            "· 超长上下文与智能体多轮，将迫使高带宽显存之外的扩展层成为标配",
            "· 控制面与数据面必须拆开演进，否则无法规模化",
            "· 没有仿真驱动，分层配置会退化为经验调参",
            "· 统一内存扩展与高速内存互联池，是突破存储墙的两条主路线",
        ],
        size=15,
        color=MID,
        spacing=7,
        bold_flags=[True, False, False, True, False, False, False, False],
    )
    # right red contrast panel
    rect(s, Inches(8.8), Inches(1.1), Inches(4.0), Inches(5.5), RED)
    textbox(s, Inches(9.05), Inches(1.4), Inches(3.5), Inches(0.4), "为何重要", size=16, bold=True, color=WHITE)
    multilines(
        s,
        Inches(9.05),
        Inches(2.0),
        Inches(3.5),
        Inches(4.2),
        [
            "显存容量增长追不上模型记忆需求",
            "",
            "命中率、首字时延、单令牌成本必须进入平台服务等级目标",
            "",
            "只看图形处理器利用率会漏掉真正瓶颈",
        ],
        size=15,
        color=WHITE,
        spacing=8,
    )
    page_chrome(s, 3, total, "核心判断")

    # p4 三跃迁
    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "路径", "｜三跃迁")
    cards = [
        ("跃迁一", "前缀命中", "跳过重复预填充\n直接降低首字时延"),
        ("跃迁二", "多轮持久", "智能体会话跨轮保留\n避免反复重建"),
        ("跃迁三", "跨实例池化", "容量与计算解耦\n网络侧共享复用"),
    ]
    for i, (tag, title, body) in enumerate(cards):
        x = Inches(0.5) + i * Inches(4.2)
        red_top_card(s, x, Inches(1.2), Inches(4.0), Inches(5.3), MOD_PINK if i == 1 else MOD)
        icon_circle(s, x + Inches(0.25), Inches(1.5))
        textbox(s, x + Inches(0.7), Inches(1.52), Inches(3), Inches(0.3), tag, size=12, color=RED, bold=True)
        textbox(s, x + Inches(0.25), Inches(2.2), Inches(3.5), Inches(0.45), title, size=22, bold=True, color=DARK)
        multilines(s, x + Inches(0.25), Inches(2.9), Inches(3.5), Inches(3.0), body.split("\n"), size=16, color=MID, spacing=10)
    page_chrome(s, 4, total, "三跃迁路径")

    # p5 指标页 - data driven
    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "指标", "｜对比与提升")
    metrics = [
        ("+50%", "卸载吞吐提升", "相对未池化基线", "内存池实测口径"),
        ("-30%", "首字时延下降", "相对未卸载路径", "内存池实测口径"),
        ("93%+", "多网卡传输效率", "数据面效率锚点", "演讲材料"),
        (">80%", "单令牌成本降幅", "相对以内存为主", "幻灯宣称口径"),
        ("<3%", "仿真配置误差", "相对经验配置", "仿真系统宣称"),
        ("七级", "介质分层栈", "显存到对象存储", "软硬结合方案"),
    ]
    for i, (num, title, desc, src) in enumerate(metrics):
        col = i % 3
        row = i // 3
        x = Inches(0.5) + col * Inches(4.2)
        y = Inches(1.15) + row * Inches(2.75)
        red_top_card(s, x, y, Inches(4.0), Inches(2.5), MOD)
        textbox(s, x + Inches(0.2), y + Inches(0.35), Inches(3.6), Inches(0.9), num, size=48, bold=True, color=RED, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.2), y + Inches(1.35), Inches(3.6), Inches(0.35), title, size=16, bold=True, color=DARK, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.2), y + Inches(1.75), Inches(3.6), Inches(0.3), desc, size=12, color=MID, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.2), y + Inches(2.1), Inches(3.6), Inches(0.25), f"来源：{src}", size=10, color=LIGHT, align=PP_ALIGN.CENTER)
    page_chrome(s, 5, total, "关键指标")

    # p6 行动建议 - dark block <30%
    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "行动", "｜落地清单")
    # left light cards
    actions = [
        ("平台侧", "把命中率、首字时延、单令牌成本写入服务等级目标，而不是只看利用率"),
        ("采购侧", "用真实负载仿真约束带宽、容量、寿命，再选型互联卡与固态盘"),
        ("架构侧", "键值控制面与推理引擎、基础设施卸载层纵向对齐"),
    ]
    for i, (h, body) in enumerate(actions):
        y = Inches(1.15) + i * Inches(1.55)
        red_top_card(s, Inches(0.5), y, Inches(7.8), Inches(1.4), MOD)
        icon_circle(s, Inches(0.7), y + Inches(0.45))
        textbox(s, Inches(1.2), y + Inches(0.25), Inches(6.8), Inches(0.35), h, size=18, bold=True, color=DARK)
        textbox(s, Inches(1.2), y + Inches(0.7), Inches(6.8), Inches(0.5), body, size=14, color=MID)
    # right dark emphasize
    rect(s, Inches(8.6), Inches(1.15), Inches(4.2), Inches(5.3), DARK)
    textbox(s, Inches(8.85), Inches(1.45), Inches(3.7), Inches(0.4), "自查三问", size=18, bold=True, color=RED)
    multilines(
        s,
        Inches(8.85),
        Inches(2.1),
        Inches(3.7),
        Inches(4.0),
        [
            "一、键值命中是否可观测、可调度？",
            "",
            "二、分层配置是否有仿真闭环？",
            "",
            "三、成本是否按令牌核算？",
        ],
        size=15,
        color=WHITE,
        spacing=6,
    )
    page_chrome(s, 6, total, "行动建议")

    thank_you_page(prs, total)
    out = OUT / "洞察-04-键值缓存基建化.pptx"
    prs.save(out)
    return out


def build_07():
    prs = new_prs()
    total = 7
    cover_page(
        prs,
        COVERS / "cover-07-fullstack.png",
        "全栈优化",
        "三件套",
        "智能体感知调度 · 设备内流水 · 跨芯算子供给",
        "演讲：资彦义 / 李陈浩文 · 阿里云智能集团",
    )
    agenda_page(
        prs,
        [
            ("01", "核心判断", "优化从单算子调参升级为三层产品能力"),
            ("02", "能力拆解", "智能体调度 · 巨型内核 · 算子智能体"),
            ("03", "指标证据", "加速比与跨平台迁移收益"),
            ("04", "行动建议", "开发闭环、会话状态与评测集"),
        ],
        total,
    )

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "判断", "｜三层能力产品化")
    red_top_card(s, Inches(0.5), Inches(1.1), Inches(8.0), Inches(5.5), MOD)
    multilines(
        s,
        Inches(0.75),
        Inches(1.4),
        Inches(7.5),
        Inches(5.0),
        [
            "一句话结论",
            "停得久不等于价值低；微秒尺度要看内核之间；跨芯竞争力取决于算子供给能否智能化。",
            "",
            "关键判断",
            "· 最近最少使用策略会误删暂停会话，迫使高成本重新预填充",
            "· 巨型内核把同步粒度从“算子完成”推进到“数据就绪”",
            "· 算子智能体把性能工程从手艺变成可迁移资产",
            "· 可复现开发闭环是规模化前提",
        ],
        size=15,
        color=MID,
        spacing=7,
        bold_flags=[True, False, False, True, False, False, False, False],
    )
    rect(s, Inches(8.8), Inches(1.1), Inches(4.0), Inches(5.5), RED)
    textbox(s, Inches(9.05), Inches(1.4), Inches(3.5), Inches(0.4), "三件套", size=16, bold=True, color=WHITE)
    multilines(
        s,
        Inches(9.05),
        Inches(2.0),
        Inches(3.5),
        Inches(4.2),
        [
            "框架层：智能体感知键值调度",
            "",
            "计算层：巨型内核设备内流水",
            "",
            "平台层：算子智能体自动供给",
        ],
        size=15,
        color=WHITE,
        spacing=8,
    )
    page_chrome(s, 3, total, "核心判断")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "拆解", "｜三层能力")
    cards = [
        ("框架层", "智能体调度", "感知运行、暂停、恢复、结束\n绿保留 / 黄准备 / 红腾挪\n减少强制预填充"),
        ("计算层", "巨型内核", "少启动 · 少搬运 · 少等待\n主机驱动 → 设备驻留\n压缩执行空洞"),
        ("平台层", "算子智能体", "主从并行探索与经验回写\n专家聚焦算法与验收\n跨芯快速适配"),
    ]
    for i, (tag, title, body) in enumerate(cards):
        x = Inches(0.5) + i * Inches(4.2)
        red_top_card(s, x, Inches(1.2), Inches(4.0), Inches(5.3), MOD if i != 1 else MOD_PINK)
        icon_circle(s, x + Inches(0.25), Inches(1.5))
        textbox(s, x + Inches(0.7), Inches(1.52), Inches(3), Inches(0.3), tag, size=12, color=RED, bold=True)
        textbox(s, x + Inches(0.25), Inches(2.2), Inches(3.5), Inches(0.45), title, size=22, bold=True, color=DARK)
        multilines(s, x + Inches(0.25), Inches(2.9), Inches(3.5), Inches(3.2), body.split("\n"), size=15, color=MID, spacing=10)
    page_chrome(s, 4, total, "能力拆解")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "指标", "｜加速证据")
    metrics = [
        ("4.88倍", "旗舰卡半精度算子", "九点五二毫秒 → 一点九五毫秒", "算子智能体案例"),
        ("2.13倍", "混合专家门控链路", "相对开源框架基线", "异构卡迁移"),
        ("1.6倍", "解码路径加速", "相对改造前", "异构卡迁移"),
        ("1.29倍", "归一化与激活链", "相对开源框架基线", "小算子融合"),
        ("1.18倍", "递推核优化", "相对改造前", "异构卡迁移"),
        ("质变", "缓存策略升级", "最近最少使用 → 价值排序", "智能体调度"),
    ]
    for i, (num, title, desc, src) in enumerate(metrics):
        col = i % 3
        row = i // 3
        x = Inches(0.5) + col * Inches(4.2)
        y = Inches(1.15) + row * Inches(2.75)
        red_top_card(s, x, y, Inches(4.0), Inches(2.5), MOD)
        textbox(s, x + Inches(0.15), y + Inches(0.35), Inches(3.7), Inches(0.9), num, size=48, bold=True, color=RED, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(1.35), Inches(3.7), Inches(0.35), title, size=15, bold=True, color=DARK, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(1.75), Inches(3.7), Inches(0.3), desc, size=12, color=MID, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(2.1), Inches(3.7), Inches(0.25), f"来源：{src}", size=10, color=LIGHT, align=PP_ALIGN.CENTER)
    page_chrome(s, 5, total, "关键指标")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "行动", "｜落地清单")
    actions = [
        ("工程化闭环", "目标—评测—剖析—定位—优化—回归，必须可复现、可门禁"),
        ("调度联动", "键值策略接入会话状态，并与池化基础设施打通"),
        ("多芯导入", "优先建设算子智能体与评测集，而不是只做模型搬运"),
    ]
    for i, (h, body) in enumerate(actions):
        y = Inches(1.15) + i * Inches(1.55)
        red_top_card(s, Inches(0.5), y, Inches(7.8), Inches(1.4), MOD)
        icon_circle(s, Inches(0.7), y + Inches(0.45))
        textbox(s, Inches(1.2), y + Inches(0.25), Inches(6.8), Inches(0.35), h, size=18, bold=True, color=DARK)
        textbox(s, Inches(1.2), y + Inches(0.7), Inches(6.8), Inches(0.5), body, size=14, color=MID)
    rect(s, Inches(8.6), Inches(1.15), Inches(4.2), Inches(5.3), DARK)
    textbox(s, Inches(8.85), Inches(1.45), Inches(3.7), Inches(0.4), "自查三问", size=18, bold=True, color=RED)
    multilines(
        s,
        Inches(8.85),
        Inches(2.1),
        Inches(3.7),
        Inches(4.0),
        [
            "一、暂停会话会被误删吗？",
            "",
            "二、优化是否可回归验证？",
            "",
            "三、跨芯是否有算子供给能力？",
        ],
        size=15,
        color=WHITE,
        spacing=6,
    )
    page_chrome(s, 6, total, "行动建议")
    thank_you_page(prs, total)
    out = OUT / "洞察-07-全栈优化三件套.pptx"
    prs.save(out)
    return out


def build_08():
    prs = new_prs()
    total = 7
    cover_page(
        prs,
        COVERS / "cover-08-future.png",
        "未来架构",
        "先拆再堆",
        "预填充解码拆分 · 注意力前馈解耦 · 仿真选型前移",
        "演讲：李文韬 · 阿里云智能集团",
    )
    agenda_page(
        prs,
        [
            ("01", "核心判断", "先拆分再堆料，先仿真再到柜"),
            ("02", "拆分路径", "阶段拆分与层内解耦可组合"),
            ("03", "指标与证据", "上下文、稀疏激活与仿真精度"),
            ("04", "行动建议", "并行推进架构与仿真开源验证"),
        ],
        total,
    )

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "判断", "｜拆分优于堆料")
    red_top_card(s, Inches(0.5), Inches(1.1), Inches(8.0), Inches(5.5), MOD)
    multilines(
        s,
        Inches(0.75),
        Inches(1.4),
        Inches(7.5),
        Inches(5.0),
        [
            "一句话结论",
            "让注意力与键值、前馈与专家各得其所；没有高保真仿真，配比无法在到货前收敛。",
            "",
            "关键判断",
            "· 模型与硬件容量、带宽、算力增长不同步",
            "· 预填充、注意力解码、前馈解码的资源画像显著不同",
            "· 层内解耦比单纯做更大超节点更贴近混合专家结构",
            "· 开源推理引擎是架构创新扩散通道",
        ],
        size=15,
        color=MID,
        spacing=7,
        bold_flags=[True, False, False, True, False, False, False, False],
    )
    rect(s, Inches(8.8), Inches(1.1), Inches(4.0), Inches(5.5), RED)
    textbox(s, Inches(9.05), Inches(1.4), Inches(3.5), Inches(0.4), "原则", size=16, bold=True, color=WHITE)
    multilines(
        s,
        Inches(9.05),
        Inches(2.0),
        Inches(3.5),
        Inches(4.2),
        [
            "先拆分，再堆料",
            "",
            "先仿真，再到柜",
            "",
            "先验证业务配比，再定采购",
        ],
        size=18,
        color=WHITE,
        spacing=10,
    )
    page_chrome(s, 3, total, "核心判断")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "路径", "｜两级拆分")
    cards = [
        ("阶段级", "预填充解码拆分", "预填充与解码分离\n经键值传递衔接\n硬件可独立配比"),
        ("层内级", "注意力前馈解耦", "注意力池与专家池往返\n每层调度分发与汇合\n贴近混合专家结构"),
        ("硬件级", "两侧专用卡", "注意力侧：大容量高带宽\n前馈侧：高效矩阵算力\n握手互联协同"),
    ]
    for i, (tag, title, body) in enumerate(cards):
        x = Inches(0.5) + i * Inches(4.2)
        red_top_card(s, x, Inches(1.2), Inches(4.0), Inches(5.3), MOD_PINK if i == 1 else MOD)
        icon_circle(s, x + Inches(0.25), Inches(1.5))
        textbox(s, x + Inches(0.7), Inches(1.52), Inches(3), Inches(0.3), tag, size=12, color=RED, bold=True)
        textbox(s, x + Inches(0.25), Inches(2.2), Inches(3.5), Inches(0.45), title, size=20, bold=True, color=DARK)
        multilines(s, x + Inches(0.25), Inches(2.9), Inches(3.5), Inches(3.2), body.split("\n"), size=15, color=MID, spacing=10)
    page_chrome(s, 4, total, "拆分路径")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "指标", "｜趋势与仿真")
    metrics = [
        ("百万级", "上下文长度压力", "十二万八千 → 约百万级", "模型趋势"),
        ("稀疏", "参数激活形态", "总参可达万亿级 / 激活约九百五十亿", "混合专家"),
        ("96%+", "仿真整体准确率", "无实物端到端与微架构", "震旦仿真"),
        ("高带宽", "前馈侧器件画像", "低容量高带宽极端点", "路线对照"),
        ("可组合", "拆分架构形态", "阶段拆分 + 层内解耦", "未来方案"),
        ("前移", "导入方式变化", "仿真 → 合入 → 联调验证", "落地节奏"),
    ]
    for i, (num, title, desc, src) in enumerate(metrics):
        col = i % 3
        row = i // 3
        x = Inches(0.5) + col * Inches(4.2)
        y = Inches(1.15) + row * Inches(2.75)
        red_top_card(s, x, y, Inches(4.0), Inches(2.5), MOD)
        textbox(s, x + Inches(0.15), y + Inches(0.35), Inches(3.7), Inches(0.9), num, size=44, bold=True, color=RED, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(1.35), Inches(3.7), Inches(0.35), title, size=15, bold=True, color=DARK, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(1.75), Inches(3.7), Inches(0.35), desc, size=12, color=MID, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.15), y + Inches(2.15), Inches(3.7), Inches(0.25), f"来源：{src}", size=10, color=LIGHT, align=PP_ALIGN.CENTER)
    page_chrome(s, 5, total, "关键指标")

    s = add_blank(prs)
    rect(s, 0, 0, W, H, BG)
    title_pair(s, Inches(0.5), Inches(0.3), "行动", "｜落地清单")
    actions = [
        ("研发并行", "拆分架构与仿真器同步推进，而不是等硬件到柜"),
        ("生态验证", "跟踪仿真合入与解耦方案开源进展，提前跑业务模型"),
        ("采购前移", "用仿真收敛两侧配比与互联设计，再做超节点与专用卡决策"),
    ]
    for i, (h, body) in enumerate(actions):
        y = Inches(1.15) + i * Inches(1.55)
        red_top_card(s, Inches(0.5), y, Inches(7.8), Inches(1.4), MOD)
        icon_circle(s, Inches(0.7), y + Inches(0.45))
        textbox(s, Inches(1.2), y + Inches(0.25), Inches(6.8), Inches(0.35), h, size=18, bold=True, color=DARK)
        textbox(s, Inches(1.2), y + Inches(0.7), Inches(6.8), Inches(0.5), body, size=14, color=MID)
    rect(s, Inches(8.6), Inches(1.15), Inches(4.2), Inches(5.3), DARK)
    textbox(s, Inches(8.85), Inches(1.45), Inches(3.7), Inches(0.4), "自查三问", size=18, bold=True, color=RED)
    multilines(
        s,
        Inches(8.85),
        Inches(2.1),
        Inches(3.7),
        Inches(4.0),
        [
            "一、是否仍在单卡堆料？",
            "",
            "二、到货前有没有仿真配比？",
            "",
            "三、注意力与前馈是否分开规划？",
        ],
        size=15,
        color=WHITE,
        spacing=6,
    )
    page_chrome(s, 6, total, "行动建议")
    thank_you_page(prs, total)
    out = OUT / "洞察-08-未来架构先拆再堆.pptx"
    prs.save(out)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    outputs = [build_04(), build_07(), build_08()]
    # remove old teal one-pagers to avoid confusion? keep them but new files are primary
    for p in outputs:
        dest = ART / p.name
        dest.write_bytes(p.read_bytes())
        print("wrote", p)
        print("artifact", dest)


if __name__ == "__main__":
    main()
