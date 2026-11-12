# -*- coding: utf-8 -*-
"""Markdown 轉 PDF（python-markdown + PyMuPDF）。"""
import os
import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import markdown

# (一般, 粗體)，沒有粗體就用一般
FONT_CANDIDATES = [
    ("msjh.ttc", "msjhbd.ttc"),      # 微軟正黑體
    ("mingliu.ttc", None),           # 新細明體
    ("msyh.ttc", "msyhbd.ttc"),      # 微軟雅黑（簡體 Windows）
]

CSS = """
@font-face { font-family: zh; src: url(%(reg)s); }
@font-face { font-family: zh; src: url(%(bold)s); font-weight: bold; }
* { font-family: zh; }
body { font-size: 10.5pt; line-height: 1.5; color: #111; }
h1 { font-size: 17pt; border-bottom: 2px solid #333; padding-bottom: 3px; }
h2 { font-size: 13.5pt; margin-top: 14pt; border-bottom: 1px solid #999; }
h3 { font-size: 11.5pt; margin-top: 10pt; }
table { border-collapse: collapse; width: 100%%; margin: 6px 0; font-size: 9.5pt; }
th, td { border: 1px solid #888; padding: 3px 5px; vertical-align: top; }
th { background-color: #eee; }
blockquote { border-left: 3px solid #aaa; margin: 6px 0; padding: 2px 10px; color: #444; }
code { font-size: 9.5pt; }
"""

PAGE = fitz.paper_rect("a4")
MARGIN = (40, 45, -40, -45)  # 左、上、右、下（點）≈ 14mm／16mm


def find_fonts() -> tuple[Path, str, str]:
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for reg, bold in FONT_CANDIDATES:
        if (fonts / reg).exists():
            b = bold if bold and (fonts / bold).exists() else reg
            return fonts, reg, b
    raise RuntimeError(f"在 {fonts} 找不到中文字型（微軟正黑體、新細明體），無法轉 PDF。")


_T = r"\d{1,2}:\d{2}:\d{2}"   # 錄音時間點一律是 hh:mm:ss；「09:30」這種一般時刻不刪
_S = r"[ \t]*"                  # 只吃水平空白，不吃換行
# 例：（00:12:47–00:13:05）、（00:06:59–00:07:09、00:13:37–00:13:50）
TIMESTAMPS = re.compile(rf"{_S}[（(]{_S}{_T}(?:{_S}[–—\-~～至]{_S}{_T})?(?:{_S}[、,，;；]{_S}{_T}(?:{_S}[–—\-~～至]{_S}{_T})?)*{_S}[）)]")


def strip_timestamps(text: str) -> str:
    return TIMESTAMPS.sub("", text)


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def ensure_breaks(text: str) -> str:
    """清單和「**背景**：」這類行前面沒空行的話，Markdown 會併成同一段。"""
    out = []
    for line in text.splitlines():
        prev = out[-1] if out else ""
        if prev.strip() and not prev.lstrip().startswith("|"):
            is_list, prev_list = LIST_ITEM.match(line), LIST_ITEM.match(prev)
            if (is_list and not prev_list) or (line.startswith("**") and not prev.lstrip().startswith("#")):
                out.append("")
        out.append(line)
    return "\n".join(out)


def md_to_pdf(src: Path, dst: Path) -> Path:
    fonts, reg, bold = find_fonts()
    # python-markdown 巢狀清單要 4 格縮排：把行首每 2 格放大成 4 格
    text = "\n".join(" " * (2 * (len(l) - len(l.lstrip(" ")))) + l.lstrip(" ")
                     for l in ensure_breaks(strip_timestamps(Path(src).read_text(encoding="utf-8"))).splitlines())
    body = markdown.markdown(text, extensions=["tables", "sane_lists"]).replace("[ ]", "☐").replace("[x]", "☑")
    story = fitz.Story(html=f"<body>{body}</body>", user_css=CSS % {"reg": reg, "bold": bold},
                       archive=fitz.Archive(str(fonts)))
    dst = Path(dst)
    # 先寫到暫存再做字型子集化，不然整套字型會讓檔案大到約 35 MB
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        raw = Path(td) / "raw.pdf"
        w = fitz.DocumentWriter(str(raw))
        more = 1
        while more:
            dev = w.begin_page(PAGE)
            more, _ = story.place(PAGE + MARGIN)
            story.draw(dev)
            w.end_page()
        w.close()
        doc = fitz.open(raw)
        doc.subset_fonts()
        doc.ez_save(str(dst))
        doc.close()
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"PDF 沒有產生：{dst}")
    return dst
