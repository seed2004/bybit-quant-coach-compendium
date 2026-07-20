#!/usr/bin/env python3
"""
Build the combined compendium PDF from the Markdown sources in docs/.

Pure-Python, depends only on reportlab. Renders a controlled Markdown subset:
  #/##/###/#### headings, - and 1. lists (one level of nesting), **bold**,
  `inline code`, > blockquotes, | tables |, ``` fenced code ```, and --- rules.

Usage:  python build_pdf.py
Output: Bybit-Quant-Coach-Compendium.pdf
"""
import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph,
    Preformatted, Spacer, Table, TableStyle, PageBreak,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = r"C:\Windows\Fonts"
OUT = os.path.join(HERE, "Bybit-Quant-Coach-Compendium.pdf")
COMPILED = "2026"

DOCS = [
    "docs/00-overview.md",
    "docs/01-design.md",
    "docs/02-implementation.md",
    "docs/03-usage.md",
    "docs/04-workflows.md",
    "docs/05-strategy-payoffs.md",
    "docs/06-lessons-and-gotchas.md",
]

# ── Fonts (Arial for broad Greek/math glyph coverage, Consolas for mono) ──────
pdfmetrics.registerFont(TTFont("Body", os.path.join(FONTS, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(FONTS, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Body-Italic", os.path.join(FONTS, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Body-BoldItalic", os.path.join(FONTS, "arialbi.ttf")))
pdfmetrics.registerFont(TTFont("Mono", os.path.join(FONTS, "consola.ttf")))
pdfmetrics.registerFont(TTFont("Mono-Bold", os.path.join(FONTS, "consolab.ttf")))
pdfmetrics.registerFontFamily(
    "Body", normal="Body", bold="Body-Bold",
    italic="Body-Italic", boldItalic="Body-BoldItalic",
)

INK = colors.HexColor("#1b1f24")
ACCENT = colors.HexColor("#1f6feb")
MUTED = colors.HexColor("#57606a")
RULE = colors.HexColor("#d0d7de")
CODEBG = colors.HexColor("#f3f5f8")

styles = getSampleStyleSheet()


def S(name, **kw):
    base = kw.pop("parent", styles["Normal"])
    return ParagraphStyle(name, parent=base, **kw)


BODY = S("body", fontName="Body", fontSize=9.7, leading=14.5, textColor=INK,
         spaceAfter=6, alignment=TA_LEFT)
H1 = S("h1", fontName="Body-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=10, spaceBefore=2)
H2 = S("h2", fontName="Body-Bold", fontSize=14.5, leading=19, textColor=ACCENT, spaceBefore=14, spaceAfter=6)
H3 = S("h3", fontName="Body-Bold", fontSize=11.6, leading=15, textColor=INK, spaceBefore=10, spaceAfter=4)
H4 = S("h4", fontName="Body-Bold", fontSize=10.2, leading=14, textColor=MUTED, spaceBefore=8, spaceAfter=3)
BULLET = S("bullet", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=3)
SUBBULLET = S("subbullet", parent=BODY, leftIndent=28, bulletIndent=17, spaceAfter=2)
QUOTE = S("quote", parent=BODY, leftIndent=12, textColor=MUTED, fontName="Body-Italic",
          borderPadding=(4, 4, 4, 8))
CODE = S("code", fontName="Mono", fontSize=8, leading=11, textColor=INK,
         backColor=CODEBG, borderPadding=6, spaceBefore=4, spaceAfter=8)
CELL = S("cell", fontName="Body", fontSize=8.4, leading=11.5, textColor=INK)
CELLH = S("cellh", fontName="Body-Bold", fontSize=8.4, leading=11.5, textColor=colors.white)
CAPTION = S("caption", parent=BODY, fontName="Body-Italic", fontSize=8.2, leading=11,
            textColor=MUTED, spaceBefore=1, spaceAfter=10, alignment=TA_CENTER)

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
USABLE_W = PAGE_W - 2 * MARGIN


def inline(text):
    """Escape XML, then re-apply markdown emphasis + inline code as reportlab markup."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r'<font face="Mono" size="8.6">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def make_table(rows):
    header, body = rows[0], rows[1:]
    ncol = len(header)
    # column widths proportional to longest cell, floored so thin columns stay legible
    weights = []
    for c in range(ncol):
        w = max([len(header[c])] + [len(r[c]) if c < len(r) else 0 for r in body])
        weights.append(max(w, 6))
    tot = sum(weights)
    col_w = [max(USABLE_W * w / tot, 26) for w in weights]
    scale = USABLE_W / sum(col_w)
    col_w = [w * scale for w in col_w]

    data = [[Paragraph(inline(c), CELLH) for c in header]]
    for r in body:
        cells = list(r) + [""] * (ncol - len(r))
        data.append([Paragraph(inline(c), CELL) for c in cells[:ncol]])

    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
    ]))
    return t


IMG_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)\s*$")


def image_flowable(alt, rel_path, base_dir):
    path = os.path.normpath(os.path.join(base_dir, rel_path))
    iw, ih = ImageReader(path).getSize()
    w = USABLE_W * 0.96
    h = w * ih / iw
    parts = [Image(path, width=w, height=h)]
    if alt.strip():
        parts.append(Paragraph(inline(alt), CAPTION))
    return KeepTogether(parts)


def parse(md, story, first_doc, base_dir):
    lines = md.split("\n")
    i, n = 0, len(lines)
    started = False
    while i < n:
        line = lines[i]

        # fenced code
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            story.append(Preformatted("\n".join(buf), CODE))
            continue

        # table (a header line followed by a |---| separator)
        if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                if re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                    i += 1; continue
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells); i += 1
            story.append(Spacer(1, 2))
            story.append(make_table(rows))
            story.append(Spacer(1, 6))
            continue

        stripped = line.strip()
        if not stripped:
            i += 1; continue

        if stripped == "---":
            i += 1; continue

        m = IMG_RE.match(stripped)
        if m:
            story.append(image_flowable(m.group("alt"), m.group("path"), base_dir))
            i += 1; continue

        if stripped.startswith("#### "):
            story.append(Paragraph(inline(stripped[5:]), H4))
        elif stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), H3))
        elif stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), H2))
        elif stripped.startswith("# "):
            if started or not first_doc:
                story.append(PageBreak())
            story.append(Paragraph(inline(stripped[2:]), H1))
            story.append(HRule())
            started = True
        elif stripped.startswith("> "):
            story.append(Paragraph(inline(stripped[2:]), QUOTE))
        elif re.match(r"^\s{2,}[-*] ", line):
            story.append(Paragraph(inline(stripped[2:]), SUBBULLET, bulletText="–"))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            story.append(Paragraph(inline(stripped[2:]), BULLET, bulletText="•"))
        elif re.match(r"^\d+\.\s", stripped):
            num, rest = stripped.split(".", 1)
            story.append(Paragraph(inline(rest.strip()), BULLET, bulletText=f"{num}."))
        else:
            story.append(Paragraph(inline(stripped), BODY))
        i += 1


class HRule(Spacer):
    """A thin horizontal rule."""
    def __init__(self):
        super().__init__(1, 8)

    def draw(self):
        self.canv.setStrokeColor(RULE)
        self.canv.setLineWidth(0.8)
        self.canv.line(0, 3, USABLE_W, 3)


def title_page(story):
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("Bybit Options-Income", S("t1", fontName="Body-Bold", fontSize=30, leading=34, textColor=INK, alignment=TA_CENTER)))
    story.append(Paragraph("Quant-Coach", S("t2", fontName="Body-Bold", fontSize=30, leading=34, textColor=ACCENT, alignment=TA_CENTER)))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Design &amp; Knowledge Compendium", S("t3", fontName="Body", fontSize=15, leading=20, textColor=MUTED, alignment=TA_CENTER)))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Concepts, models, architecture, and lessons behind a private "
                           "options-income decision-support system.<br/>Ideas only — no source code.",
                           S("t4", fontName="Body-Italic", fontSize=10.5, leading=16, textColor=MUTED, alignment=TA_CENTER)))
    story.append(Spacer(1, 40))
    story.append(Paragraph(f"Compiled {COMPILED}", S("t5", fontName="Body", fontSize=10, textColor=MUTED, alignment=TA_CENTER)))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 8)
    canvas.setFillColor(MUTED)
    if doc.page > 1:
        canvas.drawCentredString(PAGE_W / 2, 12 * mm, str(doc.page))
        canvas.drawString(MARGIN, 12 * mm, "Bybit Quant-Coach — Design & Knowledge Compendium")
        canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, "ideas only, no source")
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=18 * mm, bottomMargin=18 * mm, title="Bybit Quant-Coach Compendium")
    frame = Frame(MARGIN, 18 * mm, USABLE_W, PAGE_H - 36 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=footer)])

    story = []
    title_page(story)
    for idx, rel in enumerate(DOCS):
        full = os.path.join(HERE, rel)
        with open(full, encoding="utf-8") as f:
            parse(f.read(), story, first_doc=(idx == 0), base_dir=os.path.dirname(full))
    doc.build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
