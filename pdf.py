# -*- coding: utf-8 -*-
"""Markdown 轉 PDF：python-markdown 轉 HTML，再用 Edge（或 Chrome）headless 列印。"""
import os
import subprocess
import tempfile
from pathlib import Path

import markdown

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; font-size: 10.5pt; line-height: 1.6; color: #111; }
h1 { font-size: 17pt; border-bottom: 2px solid #333; padding-bottom: 4px; }
h2 { font-size: 13.5pt; margin-top: 18px; border-bottom: 1px solid #999; }
h3 { font-size: 11.5pt; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; }
th, td { border: 1px solid #888; padding: 4px 6px; vertical-align: top; }
th { background: #eee; }
blockquote { border-left: 3px solid #aaa; margin: 6px 0; padding: 2px 10px; color: #444; }
code { font-family: Consolas, monospace; font-size: 9.5pt; }
hr { border: 0; border-top: 1px solid #ccc; }
"""


def find_browser() -> str | None:
    pf = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files"),
          os.environ.get("LOCALAPPDATA", "")]
    for base in pf:
        for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            p = Path(base) / rel
            if p.exists():
                return str(p)
    return None


def md_to_pdf(src: Path, dst: Path) -> Path:
    """轉出 PDF 到 dst（dst 由呼叫端決定是否覆蓋）。"""
    browser = find_browser()
    if not browser:
        raise RuntimeError("找不到 Edge 或 Chrome，無法轉 PDF。")
    # python-markdown 巢狀清單要 4 格縮排：把行首每 2 格放大成 4 格
    text = "\n".join(" " * (2 * (len(l) - len(l.lstrip(" ")))) + l.lstrip(" ")
                     for l in Path(src).read_text(encoding="utf-8").splitlines())
    body = markdown.markdown(text, extensions=["tables", "sane_lists"]).replace("[ ]", "☐").replace("[x]", "☑")
    html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'
    dst = Path(dst).resolve()
    with tempfile.TemporaryDirectory() as td:
        h = Path(td) / "page.html"
        h.write_text(html, encoding="utf-8")
        if dst.exists():
            dst.unlink()
        subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={Path(td) / 'profile'}", f"--print-to-pdf={dst}", h.as_uri()],
                       timeout=180, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not dst.exists():
        raise RuntimeError(f"PDF 沒有產生：{dst}")
    return dst
