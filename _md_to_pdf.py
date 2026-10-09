"""Convert business-case.md to a PDF with working hyperlinks."""

from pathlib import Path
import subprocess
import sys

import markdown

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "business-case.md"
HTML_PATH = ROOT / "_business-case.tmp.html"
PDF_PATH = ROOT / "business-case.pdf"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

CSS = """
@page {
  size: letter;
  margin: 0.8in 0.85in 0.85in 0.85in;
}
html, body {
  margin: 0;
  padding: 0;
}
body {
  font-family: "Segoe UI", Calibri, "Helvetica Neue", Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.45;
  color: #1a1a1a;
}
h1 {
  font-size: 20pt;
  font-weight: 650;
  line-height: 1.2;
  margin: 0 0 0.6em;
}
h2 {
  font-size: 14pt;
  font-weight: 650;
  margin: 1.35em 0 0.45em;
  padding-bottom: 0.18em;
  border-bottom: 1px solid #d0d0d0;
  page-break-after: avoid;
}
h3 {
  font-size: 12pt;
  font-weight: 650;
  margin: 1.1em 0 0.35em;
  page-break-after: avoid;
}
p, ul, ol { margin: 0.55em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 0.25em 0; }
a {
  color: #0b57d0;
  text-decoration: underline;
}
code {
  font-family: Consolas, "Cascadia Mono", "Courier New", monospace;
  font-size: 9.5pt;
  background: #f3f4f6;
  padding: 0.05em 0.3em;
  border-radius: 3px;
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 9.4pt;
  line-height: 1.35;
  margin: 0.85em 0;
  page-break-inside: auto;
}
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td {
  border: 1px solid #c8c8c8;
  padding: 5px 7px;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th {
  background: #f3f4f6;
  font-weight: 650;
}
strong { font-weight: 650; }
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> int:
    text = MD_PATH.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html5",
    )
    title = "Chemical tanks at Company X's wells"
    html = HTML_TEMPLATE.format(title=title, css=CSS, body=body)
    HTML_PATH.write_text(html, encoding="utf-8")

    html_url = HTML_PATH.resolve().as_uri()
    cmd = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--no-first-run",
        "--disable-extensions",
        f"--print-to-pdf={PDF_PATH.resolve()}",
        html_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    HTML_PATH.unlink(missing_ok=True)
    print(f"Wrote {PDF_PATH} ({PDF_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
