"""Build ONE combined Hindi PDF (all 52 pages) from the translated text.

The translation was written in chunks (h1_a..h2_c) so no page could be lost while
working through the 52 source pages. This merges them into a single continuous
document with page numbers 1..52.
"""
import importlib.util

spec = importlib.util.spec_from_file_location("b", "work/build_hindi_pdfs.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

# part 1 pages 1-25, part 2 pages 1-27 -> global pages 1-52
PARTS = [
    (["work/h1_a.txt", "work/h1_b.txt", "work/h1_c.txt"], 25, 0),
    (["work/h2_a.txt", "work/h2_b.txt", "work/h2_c.txt"], 27, 25),
]


def merge():
    merged = {}
    for files, count, offset in PARTS:
        pages = {}
        for f in files:
            pages.update(b.parse(f))
        if sorted(pages) != list(range(1, count + 1)):
            raise SystemExit(f"expected pages 1..{count}, got {sorted(pages)}")
        for n, paras in pages.items():
            merged[offset + n] = paras
    return merged


if __name__ == "__main__":
    merged = merge()
    total = len(merged)
    if sorted(merged) != list(range(1, total + 1)):
        raise SystemExit("merged page numbers are not contiguous")

    # keep a single combined translation file alongside the PDF
    with open("कृषि विपणन व्यापार और मूल्य - हिंदी (पूरा पाठ).txt", "w", encoding="utf-8") as fh:
        for n in sorted(merged):
            fh.write(f"%%PAGE {n}%%\n")
            for para in merged[n]:
                fh.write(para + "\n")

    doc = b.HindiPDF()
    doc.render(merged, total)
    out = "कृषि विपणन व्यापार और मूल्य - हिंदी (पूरा).pdf"
    doc.output(out)
    print(f"wrote {out} with {total} pages")