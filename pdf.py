# -*- coding: utf-8 -*-
"""Markdown 轉 PDF（python-markdown 轉 HTML，再用 Windows 內建 Edge 列印成 PDF）。"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown

# (一般, 粗體)，沒有粗體就用一般
FONT_CANDIDATES = [
    ("msjh.ttc", "msjhbd.ttc"),      # 微軟正黑體
    ("mingliu.ttc", None),           # 新細明體
    ("msyh.ttc", "msyhbd.ttc"),      # 微軟雅黑（簡體 Windows）
]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { font-family: "%(face)s", "Microsoft JhengHei", "PMingLiU", sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-size: 10.5pt; line-height: 1.5; color: #111; margin: 0; }
tr, blockquote { page-break-inside: avoid; }
h1, h2, h3 { page-break-after: avoid; }
h1 { font-size: 17pt; border-bottom: 2px solid #333; padding-bottom: 3px; }
h2 { font-size: 13.5pt; margin-top: 14pt; border-bottom: 1px solid #999; }
h3 { font-size: 11.5pt; margin-top: 10pt; }
table { border-collapse: collapse; width: 100%%; margin: 6px 0; font-size: 9.5pt; }
th, td { border: 1px solid #888; padding: 3px 5px; vertical-align: top; }
th { background-color: #eee; }
blockquote { border-left: 3px solid #aaa; margin: 6px 0; padding: 2px 10px; color: #444; }
code { font-size: 9.5pt; }
"""



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


EDGE_CANDIDATES = (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                   r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                   r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")


def find_edge() -> str:
    """Windows 內建 Edge（微軟簽章，不會被應用程式控制擋）。"""
    for c in EDGE_CANDIDATES:
        p = Path(os.path.expandvars(c))
        if p.exists():
            return str(p)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
            p = winreg.QueryValueEx(k, "")[0]
            if Path(p).exists():
                return p
    except OSError:
        pass
    p = shutil.which("msedge")
    if p:
        return p
    raise RuntimeError("找不到 Microsoft Edge，無法轉 PDF。會議記錄 md 已存好，可用 Word 開啟 md 後另存 PDF，或請 IT 安裝 Edge。")


def md_to_html(src: Path) -> str:
    fonts, reg, bold = find_fonts()                      # 確認有中文字型（沒有就直接說明）
    # python-markdown 巢狀清單要 4 格縮排：把行首每 2 格放大成 4 格
    text = "\n".join(" " * (2 * (len(l) - len(l.lstrip(" ")))) + l.lstrip(" ")
                     for l in ensure_breaks(strip_timestamps(Path(src).read_text(encoding="utf-8"))).splitlines())
    body = markdown.markdown(text, extensions=["tables", "sane_lists"]).replace("[ ]", "☐").replace("[x]", "☑")
    face = {"msjh.ttc": "Microsoft JhengHei", "mingliu.ttc": "PMingLiU", "msyh.ttc": "Microsoft YaHei"}[reg]
    return (f"<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><style>{CSS % {'face': face}}</style>"
            f"</head><body>{body}</body></html>")


def md_to_pdf(src: Path, dst: Path, timeout: int = 120) -> Path:
    """md → HTML → Edge 無頭模式列印成 PDF（2026-11-24 起；原用 PyMuPDF，會被 Windows 應用程式控制擋）。
    用獨立暫存的 Edge 使用者資料夾，不影響使用者開著的 Edge。"""
    edge = find_edge()
    dst = Path(dst)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        html = Path(td) / "doc.html"
        html.write_text(md_to_html(src), encoding="utf-8")
        out = Path(td) / "out.pdf"
        args = [edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", f"--user-data-dir={Path(td) / 'edge'}",
                "--no-pdf-header-footer", "--print-to-pdf-no-header", f"--print-to-pdf={out}", html.as_uri()]
        try:
            subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Edge 轉 PDF 超過 {timeout} 秒沒有完成。會議記錄 md 已存好，可稍後按「重新產生 PDF」再試。")
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("Edge 沒有產生 PDF。會議記錄 md 已存好，可稍後按「重新產生 PDF」再試。")
        shutil.copyfile(out, dst)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"PDF 沒有產生：{dst}")
    return dst
