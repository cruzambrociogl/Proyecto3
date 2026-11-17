#!/usr/bin/env python3
"""Build a PDF from a markdown document: markdown -> HTML -> PDF with headless Chrome.

  python3 docs/build_pdf.py                                  # docs/protocol-document.md -> docs/protocol-document.pdf
  python3 docs/build_pdf.py docs/documento-protocolo.md      # any other document
  python3 docs/build_pdf.py IN.md --out OUT.pdf --keep-html  # keep the HTML next to the PDF

Needs the `markdown` package (pip install --user markdown) and Google Chrome.
Images are referenced relative to the markdown file.
"""
import argparse
import html
import os
import re
import subprocess
import sys
import tempfile

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: Letter; margin: 2cm 1.9cm; }
html { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }
body { margin: 0; }
h1 { font-size: 21pt; line-height: 1.2; margin: 0 0 6pt; }
h1 + p { color: #333; margin-top: 0; }
h2 { font-size: 15pt; margin: 20pt 0 6pt; break-after: avoid; }
h3 { font-size: 12pt; margin: 14pt 0 4pt; break-after: avoid; }
p, ul, ol { margin: 5pt 0; }
li { margin: 2pt 0; }
code { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 8.8pt; background: #f2f2f2; padding: 0 2pt; border-radius: 2pt; }
pre { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 8.2pt; line-height: 1.3; background: #f7f7f7;
      border: 1px solid #ddd; border-radius: 3pt; padding: 7pt 9pt; break-inside: avoid; white-space: pre; overflow: hidden; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 7pt 0; font-size: 9pt; }
th, td { border: 1px solid #c8c8c8; padding: 3.5pt 5pt; text-align: left; vertical-align: top; }
th { background: #efefef; font-weight: 600; }
tr { break-inside: avoid; }
thead { display: table-header-group; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #bbb; color: #444; }
a { color: #1a4f9c; text-decoration: none; }
img { max-width: 100%; }
"""


def nest_lists(text):
    """Python-Markdown needs 4 spaces for a nested list; the docs use 2 or 3 (GitHub style)."""
    out, fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence:
            line = re.sub(r"^ {2,3}(?=[-*] |\d+\. )", "    ", line)
        out.append(line)
    return "\n".join(out)


def build(src, out, keep_html):
    with open(src, encoding="utf-8") as f:
        text = nest_lists(f.read())
    m = re.search(r"^# (.+)$", text, re.M)
    title = m.group(1).strip() if m else os.path.basename(src)
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    page = ('<!doctype html><html><head><meta charset="utf-8"><title>%s</title><style>%s</style></head>'
            "<body>%s</body></html>" % (html.escape(title), CSS, body))
    # the HTML sits next to the markdown so relative image paths resolve
    folder = os.path.dirname(os.path.abspath(src))
    fd, tmp = tempfile.mkstemp(suffix=".html", prefix=".build-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(page)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--print-to-pdf=" + os.path.abspath(out), "file://" + tmp],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    finally:
        if keep_html:
            os.replace(tmp, os.path.splitext(out)[0] + ".html")
        else:
            os.remove(tmp)
    print("wrote", out)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="markdown -> PDF via headless Chrome")
    ap.add_argument("src", nargs="?", default=os.path.join(here, "protocol-document.md"))
    ap.add_argument("--out", help="PDF path (default: next to the source, same name)")
    ap.add_argument("--keep-html", action="store_true")
    args = ap.parse_args()
    out = args.out or os.path.splitext(args.src)[0] + ".pdf"
    if not os.path.exists(CHROME):
        sys.exit("Google Chrome not found at " + CHROME)
    build(args.src, out, args.keep_html)


if __name__ == "__main__":
    main()
