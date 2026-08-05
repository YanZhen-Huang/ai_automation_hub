import os
import re
from pathlib import Path

from fpdf import FPDF

SRC = Path(r"C:\Users\hzy12\ai_automation_hub\docs\guide.md")
OUT = Path(r"C:\Users\hzy12\ai_automation_hub\docs\使用手册.pdf")
FONT = r"C:\Windows\Fonts\simhei.ttf"


def clean(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"^\s*[-*>]\s*", "", t)
    return t.strip()


def blocks():
    out = []
    code = False
    buf = []
    for line in open(SRC, encoding="utf-8"):
        s = line.rstrip("\n").strip()
        if s.startswith("```"):
            if code:
                out.append(("code", "\n".join(buf)))
                buf = []
            code = not code
            continue
        if code:
            buf.append(line.rstrip("\n"))
            continue
        if not s or s == "---":
            continue
        if s.startswith("#### "):
            out.append(("h4", clean(s[5:])))
        elif s.startswith("### "):
            out.append(("h3", clean(s[4:])))
        elif s.startswith("## "):
            out.append(("h2", clean(s[3:])))
        elif s.startswith("# "):
            out.append(("h1", clean(s[2:])))
        elif s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            out.append(("row", cells))
        elif re.match(r"^\d+\.", s) or s.startswith("- ") or s.startswith("* "):
            out.append(("item", clean(s)))
        else:
            out.append(("para", clean(s)))
    return out


class Doc(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("hei", "", FONT)
        self.add_page()
        self.set_margins(14, 12, 14)

    def cw(self):
        return self.w - self.l_margin - self.r_margin

    def heading(self, text, size, yb=5):
        self.set_x(self.l_margin)
        self.ln(yb)
        self.set_font("hei", size=size)
        self.set_text_color(20, 20, 20)
        self.multi_cell(self.cw(), size * 0.55, text)

    def body(self, text, size=9.5):
        self.set_x(self.l_margin)
        self.set_font("hei", size=size)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self.cw(), size * 0.52, text)
        self.ln(1)

    def render_table(self, header, rows):
        self.set_font("hei", size=8)
        with super().table(borders_layout="ALL", line_height=1.5,
                           padding=1, text_align="LEFT",
                           first_row_as_headings=False) as tb:
            for cells in [header] + rows:
                r = tb.row()
                for c in cells:
                    r.cell(clean(c))
        self.set_margins(14, 12, 14)
        self.set_x(self.l_margin)
        self.ln(2)


def main():
    doc = Doc()
    rows_pending = []
    for btype, content in blocks():
        if btype == "row":
            rows_pending.append(content)
            continue
        if rows_pending:
            doc.render_table(rows_pending[0], rows_pending[1:])
            rows_pending = []
        if btype == "h1":
            doc.heading(content, 16)
        elif btype == "h2":
            doc.heading(content, 13)
        elif btype == "h3":
            doc.heading(content, 11)
        elif btype == "h4":
            doc.heading(content, 10)
        elif btype == "para":
            doc.body(content)
        elif btype == "item":
            doc.body("\u00b7 " + content)
        elif btype == "code":
            doc.set_x(doc.l_margin)
            doc.set_font("hei", size=8)
            doc.set_text_color(90, 90, 90)
            doc.multi_cell(doc.cw(), 4.2, content)
            doc.ln(2)
    if rows_pending:
        doc.render_table(rows_pending[0], rows_pending[1:])
    doc.output(str(OUT))
    return os.path.exists(OUT)


if __name__ == "__main__":
    ok = main()
    print("PDF written:", ok, "->", OUT)
