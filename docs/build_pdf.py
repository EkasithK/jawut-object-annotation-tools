"""Render a Markdown document in this folder to a styled PDF.

    uv run --with markdown --with weasyprint python docs/build_pdf.py
    uv run --with markdown --with weasyprint python docs/build_pdf.py \
        HELMET_MIGRATION.md

Images are resolved relative to this folder, so `guide/01-welcome.png` works.
"""

import sys
from pathlib import Path

import markdown
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent

CSS = """
@page {
  size: A4; margin: 1.7cm 1.5cm 1.6cm;
  @bottom-center { content: counter(page) " / " counter(pages);
    font-size: 8.5px; color: #9aa3b2; }
}
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10.5px;
  line-height: 1.55; color: #1c2430; }

h1 { font-size: 22px; color: #b4431a; margin: 0 0 2px;
  border-bottom: 3px solid #b4431a; padding-bottom: 7px; }
h2 { font-size: 15px; color: #0e1013; margin-top: 26px;
  border-bottom: 1px solid #d4dae2; padding-bottom: 4px;
  page-break-after: avoid; }
h3 { font-size: 12px; color: #33404f; margin-top: 16px; page-break-after: avoid; }

p, li { font-size: 10.5px; }
li { margin: 2px 0; }

/* Screenshots: full width, framed, and never split across a page. */
img { max-width: 100%; height: auto; display: block; margin: 10px auto 4px;
  border: 1px solid #c9d2dc; border-radius: 3px; page-break-inside: avoid; }

code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.2px;
  background: #eef1f5; padding: 1px 4px; border-radius: 3px; color: #1c2430; }
pre { background: #f5f7fa; border: 1px solid #dde3ea; border-radius: 4px;
  padding: 9px 11px; font-size: 9px; line-height: 1.45; white-space: pre-wrap;
  page-break-inside: avoid; }
pre code { background: none; padding: 0; }

table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.6px;
  page-break-inside: avoid; }
th { background: #23303f; color: #fff; text-align: left; padding: 5px 8px;
  font-weight: 600; }
td { border: 1px solid #d6dee4; padding: 4px 8px; vertical-align: top; }
tr:nth-child(even) td { background: #f6f8fa; }

blockquote { border-left: 3px solid #ff7a3d; background: #fff5f0;
  margin: 12px 0; padding: 8px 14px; color: #3a2419; page-break-inside: avoid; }
blockquote p { margin: 0; }

strong { color: #0e1013; }
hr { border: none; border-top: 1px solid #e2e7ee; margin: 22px 0; }
"""


def build(src: Path, out: Path) -> None:
    html_body = markdown.markdown(
        src.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    doc = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body>{html_body}</body></html>"
    )
    HTML(string=doc, base_url=str(ROOT)).write_pdf(str(out))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "USER_GUIDE.md"
    source = ROOT / name
    if not source.is_file():
        raise SystemExit(f"{source} does not exist")
    build(source, source.with_suffix(".pdf"))
