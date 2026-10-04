"""Assemble Hindi PDFs from translated page-marked text files.

Two fonts are registered because neither covers both scripts: NotoSansDevanagari
lacks Latin glyphs, NotoSans lacks Devanagari. Text is split into runs at script
boundaries (never inside a Devanagari word, so shaping/conjuncts stay intact)
and each run is drawn with the font that has the glyphs.
"""
import re
import sys
from fpdf import FPDF

FDIR = "/home/daytona/.fonts"
FOOTER = "कृषि विपणन, व्यापार और मूल्य — www.AgriMoon.Com"

DEV_BOLD = f"{FDIR}/NotoSansDevanagari-Bold.ttf"
DEV_REG = f"{FDIR}/NotoSansDevanagari.ttf"
LAT_BOLD = f"{FDIR}/NotoSans-Bold.ttf"
LAT_REG = f"{FDIR}/NotoSans-Regular.ttf"


def is_dev(ch):
    """True for Devanagari letters and the marks that bind to them."""
    o = ord(ch)
    return (0x0900 <= o <= 0x097F) or o in (0x200C, 0x200D)


def is_marks(ch):
    """Combining marks must stay attached to the base character before them."""
    o = ord(ch)
    return o in (0x0900, 0x0901, 0x0902, 0x0903, 0x093A, 0x093B, 0x200C, 0x200D) or (
        0x093C <= o <= 0x094F) or (0x0951 <= o <= 0x0957) or (0x0962 <= o <= 0x0963)


def split_runs(text):
    """Split into (is_devanagari, chunk) runs.

    Boundaries are placed on script changes, but never between a Devanagari
    base character and a following combining mark, so shaping, conjuncts and
    matras stay intact.
    """
    runs = []
    for tok in re.findall(r"\S+|\s+", text):
        cur, curdev = "", None
        for ch in tok:
            d = is_dev(ch)
            # A split is only allowed when the new char does not attach to the
            # character before it (matras, ZWJ/ZWNJ, nukta, anusvara ...).
            if cur and d != curdev and not is_marks(ch):
                runs.append((curdev, cur))
                cur = ""
            curdev = d
            cur += ch
        if cur:
            runs.append((curdev, cur))
    return runs


def parse(path):
    """Return {page_no: [paragraph, ...]} preserving order."""
    pages, cur = {}, None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = re.match(r"^%%PAGE (\d+)%%$", line.strip())
            if m:
                cur = int(m.group(1))
                pages[cur] = []
                continue
            if cur is None:
                continue
            t = line.strip()
            if t:
                pages[cur].append(t)
    return pages


def is_heading(t):
    """Short standalone lines that read as headings render bold."""
    if len(t) > 90 or t.endswith(("।", "?", ":", ";", ",")):
        return False
    return not t[0].isdigit()


class HindiPDF(FPDF):
    """A4 document that draws mixed-script lines itself so both fonts are used."""

    LH = 6.9          # line height in mm
    BODY = 11
    W = 0             # usable width, set in __init__

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(True, margin=18)
        self.set_margins(20, 18, 20)
        self.W = self.w - 40
        # fpdf2 keys fonts by family+style, so the bold faces get their own family.
        self.add_font("dev", "", DEV_REG)
        self.add_font("devb", "B", DEV_BOLD)
        self.add_font("lat", "", LAT_REG)
        self.add_font("latb", "B", LAT_BOLD)
        self.font_key = ("dev", "")
        self.set_font("dev", size=self.BODY)
        self.page_no = 0

    def font_name(self, dev, bold):
        """Return the (family, style) pair that has the glyphs for this run."""
        return (("devb", "B") if bold else ("dev", "")) if dev else (
            ("latb", "B") if bold else ("lat", ""))

    def _w(self, txt, dev, bold):
        prev, self.font_key = self.font_key, self.font_name(dev, bold)
        self.set_font(*self.font_key, size=self.BODY)
        w = self.get_string_width(txt)
        self.font_key = prev
        return w

    def _draw_line(self, x, y, parts, bold):
        """parts = [(dev, text), ...] already fit on one line."""
        for dev, txt in parts:
            self.set_font(*self.font_name(dev, bold), size=self.BODY)
            self.text(x, y, txt)
            x += self.get_string_width(txt)
        return x

    def flow(self, text, align="J", bold=False):
        """Typeset one paragraph, wrapping across lines.

        Every token is emitted exactly once: wrapping moves the token that did
        not fit to the next line instead of dropping it.
        """
        runs = split_runs(text)
        lines, cur, x = [], [], 0.0
        for dev, tok in runs:
            if tok.isspace():
                if cur:
                    cur.append((dev, tok))
                    x += self._w(tok, dev, bold)
                continue
            tw = self._w(tok, dev, bold)
            if x + tw > self.W and cur:
                while cur and cur[-1][1].isspace():
                    cur.pop()
                lines.append(cur)
                cur, x = [], 0.0
            cur.append((dev, tok))
            x += tw
        if cur:
            lines.append(cur)

        for line in lines:
            if self.get_y() + self.LH > self.h - 18:
                self.add_page()
            y = self.get_y() + self.LH - 1.6
            if align == "J" and len(line) > 1:
                gaps = sum(1 for _, t in line if t.isspace())
                used = sum(self._w(t, d, bold) for d, t in line)
                if gaps:
                    extra = max(0.0, (self.W - used)) / gaps
                    grown = []
                    for d, t in line:
                        if t.isspace():
                            sp = self._w(" ", d, bold)
                            n = 1 + int(extra / sp) if sp > 0 else 1
                            grown.append((d, " " * max(1, n)))
                        else:
                            grown.append((d, t))
                    self._draw_line(20.0, y, grown, bold)
                    self.set_y(y + 1.6 - self.LH)
                    continue
            self._draw_line(20.0, y, line, bold)
            self.set_y(y + 1.6 - self.LH)
        return len(lines)

    def footer(self):
        self.set_y(-14)
        self.set_font("lat", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"{self.page_no}", align="C")
        self.set_text_color(0, 0, 0)

    def render(self, pages, expected):
        got = sorted(pages)
        if got != list(range(1, expected + 1)):
            missing = sorted(set(range(1, expected + 1)) - set(got))
            extra = sorted(set(got) - set(range(1, expected + 1)))
            sys.exit(f"page mismatch: missing={missing} extra={extra}")
        for n in range(1, expected + 1):
            self.add_page()
            self.page_no += 1
            self.set_y(18)
            for d, txt in split_runs(f"पृष्ठ {n}"):
                self.set_font(*self.font_name(d, True), size=12)
                self.cell(0, 7, txt, align="R" if d else "L")
            self.set_y(28)
            for para in pages[n]:
                bold = is_heading(para)
                align = "J" if len(para) > 120 else "L"
                self.flow(para, align, bold=bold)
                self.ln(1.0)


def build(text_files, expected_pages, out_path):
    merged = {}
    for f in text_files:
        for k, v in parse(f).items():
            if k in merged:
                raise SystemExit(f"duplicate page {k} in {f}")
            merged[k] = v
    doc = HindiPDF()
    doc.render(merged, expected_pages)
    doc.output(out_path)
    print(f"wrote {out_path} from {len(merged)} source pages")


if __name__ == "__main__":
    build(["work/h1_a.txt", "work/h1_b.txt", "work/h1_c.txt"], 25,
          "कृषि विपणन व्यापार और मूल्य - हिंदी - भाग 1 (1-25).pdf")
    build(["work/h2_a.txt", "work/h2_b.txt", "work/h2_c.txt"], 27,
          "कृषि विपणन व्यापार और मूल्य - हिंदी - भाग 2 (26-52).pdf")
